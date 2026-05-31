"""Conversation summary service.

Two operations:

  1. summarize_conversation(conversation_id) — generates / updates the summary
     for one conversation. Runs as a background task after a stream finishes.
     Idempotent — if the conversation hasn't grown since last summarization,
     does nothing.

  2. retrieve_related_summaries(user_id, query, exclude_id) — for a given user
     message in a NEW chat, finds up to 3 other conversations whose summary
     is semantically close. The chat router injects these into the system
     prompt so the agent can reference past discussions.

Design notes:
  - We summarize after every Nth turn AND when the conversation idles. The
    idle case is handled implicitly: any chat router invocation triggers a
    re-summarize if the count threshold is crossed.
  - Summary content is intentionally short (2-4 sentences). Long summaries
    bloat the prompt when multiple are retrieved.
  - We use Haiku, not Sonnet — summary quality is forgiving and 1/15 the cost.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.llm_v2 import get_utility_llm
from app.services.embeddings import embed_document, embed_query
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)


# Re-summarize a conversation every N new messages.
SUMMARIZE_EVERY_N_MESSAGES = 10

# Cap on summary length — keeps retrieved-prompt size sane when multiple
# summaries are injected.
SUMMARY_MAX_CHARS = 400


SUMMARY_PROMPT = """Summarize this conversation between a user and their personal AI assistant.

Write 2-4 sentences capturing:
- The main topic(s) discussed
- Any decisions made or conclusions reached
- Any concrete commitments, plans, or follow-ups

Write in third person about "the user". Match the language of the conversation \
(English if English, Indonesian if Indonesian, etc.). Be specific where it adds \
value — vague summaries help nothing.

Output ONLY the summary text. No preamble, no headers, no quotes."""


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


async def summarize_conversation(conversation_id: str) -> None:
    """Generate or update the summary for one conversation.

    Idempotent. Runs as a background task; failures are logged, not raised.
    """
    # Look up conversation + the latest message ID.
    convo_res = safe_execute(
        lambda sb: sb.table("conversations")
        .select("id, user_id, summarized_through, summary")
        .eq("id", conversation_id)
        .maybe_single()
        .execute()
    )
    if not convo_res or not convo_res.data:
        log.warning("summarize: conversation not found id=%s", conversation_id[:8])
        return

    convo = convo_res.data
    user_id = convo["user_id"]

    # Count messages since last summarization. Cheap; avoids re-running on every turn.
    msgs_res = safe_execute(
        lambda sb: sb.table("messages")
        .select("id, role, content, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    messages = msgs_res.data or []

    # Minimum 2 messages (1 user + 1 assistant) to summarize. This is intentionally
    # low — short chats often contain durable plans (e.g. "give me a diet plan")
    # that the user will want to retrieve from new chats.
    if len(messages) < 2:
        return

    # If we have a previous summary AND we haven't accumulated N new messages
    # since the last summarize point, skip.
    if convo.get("summarized_through") and convo.get("summary"):
        through_id = convo["summarized_through"]
        try:
            through_idx = next(
                i for i, m in enumerate(messages) if m["id"] == through_id
            )
            new_messages_since = len(messages) - 1 - through_idx
            if new_messages_since < SUMMARIZE_EVERY_N_MESSAGES:
                return
        except StopIteration:
            # the summarized_through id is gone (message was deleted); fall through and re-summarize
            pass

    # Compose conversation text for Haiku. Cap at 8000 chars — long enough
    # for ~30 turns, short enough to keep latency bounded.
    convo_text_parts: list[str] = []
    running = 0
    for m in messages:
        line = f"{m['role'].upper()}: {m['content']}\n"
        if running + len(line) > 8000:
            convo_text_parts.append("[earlier turns omitted]\n")
            break
        convo_text_parts.append(line)
        running += len(line)
    convo_text = "".join(convo_text_parts)

    try:
        llm = get_utility_llm()
        summary_prompt = f"{SUMMARY_PROMPT}\n\nConversation:\n{convo_text}\n\nSummary:"
        summary = (
            await llm.generate_text(
                prompt=summary_prompt,
                max_tokens=300,
                temperature=0.2,
            )
        ).strip()[:SUMMARY_MAX_CHARS]
        if not summary:
            log.warning("summarize: utility LLM returned empty summary")
            return
    except Exception as exc:  # noqa: BLE001
        log.warning("summarize: utility LLM call failed: %s", exc)
        return

    # Embed the summary for cross-conversation retrieval.
    try:
        embedding = await embed_document(summary)
    except Exception as exc:  # noqa: BLE001
        log.warning("summarize: embedding failed: %s", exc)
        return

    last_msg_id = messages[-1]["id"]
    safe_execute(
        lambda sb: sb.table("conversations")
        .update(
            {
                "summary": summary,
                "summary_embedding": embedding,
                "summarized_through": last_msg_id,
                "summarized_at": "now()",
            }
        )
        .eq("id", conversation_id)
        .execute()
    )

    log.info(
        "summarize: user=%s convo=%s summary='%s'",
        user_id[:8],
        conversation_id[:8],
        summary[:80],
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


async def retrieve_related_summaries(
    *,
    user_id: str,
    query_text: str,
    exclude_conversation_id: str,
    limit: int = 3,
    min_similarity: float = 0.55,
) -> list[dict[str, Any]]:
    """Return up to `limit` other conversations whose summary is semantically
    close to the user's current message.

    Returns a list of dicts: {id, title, summary, updated_at, similarity}.
    Empty list on any failure — retrieval is best-effort context, not critical.
    """
    try:
        query_embedding = await embed_query(query_text)
    except Exception as exc:  # noqa: BLE001
        log.warning("summary retrieval: embed failed: %s", exc)
        return []

    try:
        result = safe_execute(
            lambda sb: sb.rpc(
                "match_conversation_summaries",
                {
                    "p_user_id": user_id,
                    "p_query_embedding": query_embedding,
                    "p_exclude_id": exclude_conversation_id,
                    "p_match_count": limit,
                    "p_min_similarity": min_similarity,
                },
            ).execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("summary retrieval: RPC failed: %s", exc)
        return []

    return result.data or []
