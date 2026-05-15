"""Memory: extract durable facts from conversations, retrieve them when relevant.

Two main operations:

1. extract_and_save(user_id, conversation_id, messages)
   Runs after a chat turn finishes. Asks Claude to identify any durable facts
   worth remembering, then saves them with embeddings. This is a background
   task — the user has already seen Claude's reply by the time this runs.

2. retrieve_relevant(user_id, query_text, limit=8)
   Runs before a chat turn. Embeds the user's message, finds memories with
   similar embeddings, returns them as a list. The chat router formats these
   into the system prompt so Claude "knows" them.

Design notes:
- Extraction prompt is intentionally conservative — we'd rather miss a fact
  than store a dozen ephemeral ones.
- We cap memories per extraction at 5 to avoid runaway growth.
- We don't deduplicate yet — for personal scale, duplicates aren't a problem
  until you have hundreds. Adding dedup is a Phase 2.5 improvement.
"""

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.services.claude import get_claude
from app.services.embeddings import embed_document, embed_query
from app.services.supabase_client import get_supabase

log = logging.getLogger(__name__)

# Cap how many memories we ask Claude to extract per turn. Hard limit prevents
# the model from going wild on long conversations.
MAX_MEMORIES_PER_EXTRACTION = 5

# When extracting a new memory, if there's already a stored memory with cosine
# similarity above this threshold, treat it as a duplicate and skip insertion.
# Tuned conservatively — we'd rather skip a genuine new memory than accumulate
# 4 paraphrased versions of "User lives in Jakarta".
DEDUP_SIMILARITY_THRESHOLD = 0.92


# ---------------------------------------------------------------------------
# Pydantic shape for what we ask Claude to return
# ---------------------------------------------------------------------------

class ExtractedMemory(BaseModel):
    content: str = Field(min_length=3, max_length=500)
    kind: Literal["fact", "preference", "context"]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You analyze a conversation between a user and an AI assistant. \
Your job is to identify DURABLE facts about the user that would be useful to remember in \
future conversations.

Output a JSON array. Each item has:
  - content: the fact, written in third person about "the user" (e.g. "User lives in Jakarta")
  - kind: one of "fact" (objective), "preference" (likes/dislikes), or "context" (current situation)

Be CONSERVATIVE. Only extract facts that are:
- Clearly stated by the user (not by the assistant)
- Likely to remain true beyond this conversation
- Specific enough to be useful (not "user said hello")

If there's nothing worth remembering, return [].

Output ONLY the JSON array. No prose, no markdown fences, no commentary.

Examples of what to extract:
- User mentioned they work as a software engineer in Jakarta → \
  [{"content": "User works as a software engineer", "kind": "fact"}, \
   {"content": "User lives in Jakarta", "kind": "fact"}]
- User said they don't like dark themes → \
  [{"content": "User prefers light themes over dark themes", "kind": "preference"}]
- User is currently planning a wedding for September → \
  [{"content": "User is planning a wedding for September", "kind": "context"}]

Examples of what NOT to extract:
- Generic chat ("user said hello")
- Things the user asked but didn't reveal about themselves
- Information the assistant provided
"""


async def extract_and_save(
    user_id: str,
    conversation_id: str,
    recent_messages: list[dict],
) -> int:
    """Extract memories from a conversation slice and save them.

    `recent_messages` should be the last few turns — typically just the
    user message that triggered this and the assistant's reply, but
    extending to a few prior turns gives more context.

    Returns the number of memories saved.
    """
    if not recent_messages:
        return 0

    # Format the conversation for Claude.
    transcript = "\n\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent_messages
    )

    try:
        claude = get_claude()
        response = await claude.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )
        # Claude returns a list of content blocks; we expect a single text block.
        text_block = next(
            (b for b in response.content if b.type == "text"), None
        )
        if not text_block:
            return 0
        raw = text_block.text.strip()
    except Exception as exc:
        log.warning("memory extraction: Claude call failed: %s", exc)
        return 0

    # Parse. Be defensive — Claude sometimes wraps JSON in fences despite
    # being told not to.
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("memory extraction: not valid JSON: %r", raw[:200])
        return 0

    if not isinstance(parsed, list):
        return 0

    # Validate via Pydantic; skip anything malformed.
    valid: list[ExtractedMemory] = []
    for item in parsed[:MAX_MEMORIES_PER_EXTRACTION]:
        try:
            valid.append(ExtractedMemory.model_validate(item))
        except Exception:  # noqa: BLE001
            continue

    if not valid:
        return 0

    # Embed and insert. We embed sequentially because Voyage's free tier
    # rate limits requests-per-minute — concurrent calls can trip it.
    supabase = get_supabase()
    rows = []
    for mem in valid:
        try:
            embedding = await embed_document(mem.content)
        except Exception as exc:  # noqa: BLE001
            log.warning("memory extraction: embed failed: %s", exc)
            continue

        # Dedup check — if a near-identical memory already exists, skip.
        # This is what stops the "User lives in Jakarta" / "User is in Jakarta"
        # / "User's location is Jakarta" pile-up over time.
        try:
            existing = supabase.rpc(
                "match_memories",
                {
                    "p_user_id": user_id,
                    "p_query_embedding": embedding,
                    "p_match_count": 1,
                },
            ).execute()
            top = (existing.data or [None])[0]
            if top and top.get("similarity", 0) >= DEDUP_SIMILARITY_THRESHOLD:
                log.info(
                    "memory extraction: skipped dup '%s' (matches '%s' @ %.2f)",
                    mem.content[:60],
                    top.get("content", "")[:60],
                    top["similarity"],
                )
                continue
        except Exception as exc:  # noqa: BLE001
            # Dedup is best-effort. Fall through to insert if the check fails.
            log.warning("memory dedup check failed: %s", exc)

        rows.append(
            {
                "user_id": user_id,
                "content": mem.content,
                "kind": mem.kind,
                "embedding": embedding,
                "source": "auto",
                "source_conversation_id": conversation_id,
            }
        )

    if not rows:
        return 0

    supabase.table("memories").insert(rows).execute()
    log.info("memory extraction: saved %d memories", len(rows))
    return len(rows)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

# A similarity threshold below which we treat a memory as "irrelevant" and
# don't inject it. Cosine similarity ranges 0..1 (after our `1 - distance`
# transform in the SQL function). 0.5 is a sensible floor for voyage-3.5-lite
# but you may want to tune this after using it.
MIN_SIMILARITY = 0.5


async def retrieve_relevant(user_id: str, query_text: str, limit: int = 8) -> list[dict]:
    """Find memories most relevant to the user's current message.

    Returns a list of {id, content, kind, similarity} dicts, ordered by
    similarity (most relevant first), filtered above MIN_SIMILARITY.
    """
    try:
        query_embedding = await embed_query(query_text)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory retrieval: embed failed: %s", exc)
        return []

    supabase = get_supabase()
    result = supabase.rpc(
        "match_memories",
        {
            "p_user_id": user_id,
            "p_query_embedding": query_embedding,
            "p_match_count": limit,
        },
    ).execute()

    rows = result.data or []
    return [r for r in rows if r.get("similarity", 0) >= MIN_SIMILARITY]


def format_for_prompt(memories: list[dict]) -> str:
    """Render retrieved memories into a system-prompt-ready string."""
    if not memories:
        return ""
    lines = ["What you know about the user from past conversations:"]
    for m in memories:
        lines.append(f"- {m['content']}")
    return "\n".join(lines)
