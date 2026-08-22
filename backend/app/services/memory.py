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
from app.services.memory_hygiene import sanitize_memory_rows
from app.services.goal_source_rules import convert_goal_duplicate_rows
from app.services.memory_supersession import apply_memory_supersession

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
    kind: Literal["fact", "preference", "context", "plan"]
    memory_key: str = Field(min_length=2, max_length=120)
    memory_value: str = Field(min_length=2, max_length=300)
    category: str = Field(min_length=2, max_length=80)
    confidence: float = Field(default=0.72, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You analyze a conversation between a user and an AI assistant. \
Your job is to identify DURABLE facts and plans that would be useful to remember in \
future conversations.

Output a JSON array. Each item has:
  - content: written in third person about "the user" (e.g. "User lives in Jakarta")
  - kind: one of:
      - "fact" — objective truth about the user
      - "preference" — likes/dislikes
      - "context" — current situation
      - "plan" — a concrete plan, recommendation, or structured advice the \
assistant gave the user that the user seems to have accepted or asked to follow
  - memory_key: a concise stable key for the memory, snake_case, not generic
      examples: timezone, preferred_name, food_preference, communication_style
  - memory_value: the exact useful value to remember
      examples: GMT+7, Beb, prefers concise answers, avoids spicy food
  - category: one of identity, preferences, context, goals, routines, relationships, projects, constraints, important_dates
  - confidence: number from 0.0 to 1.0

Be CONSERVATIVE. Only extract things that are:
- Clearly stated by the user (for fact/preference/context), OR
- A concrete actionable plan the assistant gave that the user did not reject (for plan)
- Specific enough to be useful in a future conversation
- Likely to remain relevant beyond this conversation

For "plan" entries, capture the CONCRETE substance: numbers, structure, key items. \
Not "User got a diet plan" — instead "Diet plan: 1800 kcal/day, no carbs after 6pm, \
high protein breakfast (eggs/oats), lunch with vegetables and lean protein, light \
dinner before 7pm".

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
- Assistant gave a workout plan and user said "thanks, will try it" → \
  [{"content": "Workout plan: 4x/week upper-lower split, 45min sessions, \
focus compound lifts (squat, bench, deadlift, OHP), progressive overload weekly", \
"kind": "plan"}]

Examples of what NOT to extract:
- Generic chat ("user said hello")
- Greeting/filler/acknowledgement/test messages like "hai", "halo", "oke", "done", "test"
- Very short fragments that do not contain a durable fact, preference, goal, identity detail, routine, constraint, or plan
- Anything where you cannot produce a clear memory_key and memory_value
- Things the user asked but didn't reveal about themselves
- General information the assistant provided that wasn't a concrete plan for the user
- A plan the user explicitly rejected or said they wouldn't follow
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
                "category": mem.category,
                "structured_field": mem.memory_key,
                "structured_value": mem.memory_value,
                "confidence": mem.confidence,
                "embedding": embedding,
                "source": "auto",
                "source_priority": "explicit_user_statement",
                "source_conversation_id": conversation_id,
            }
        )

    rows = sanitize_memory_rows(rows)
    rows = convert_goal_duplicate_rows(user_id=user_id, rows=rows)
    rows = apply_memory_supersession(user_id=user_id, rows=rows)

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
PERSONAL_CUE_MIN_SIMILARITY = 0.40


async def _legacy_retrieve_relevant_simple(user_id: str, query_text: str, limit: int = 8) -> list[dict]:
    """Find memories most relevant to the user's current message.

    Returns a list of {id, content, kind, similarity} dicts, ordered by
    similarity (most relevant first), filtered above MIN_SIMILARITY.
    """

    from app.services.memory_retrieval_gate import should_retrieve_memory

    gate_decision = should_retrieve_memory(query_text)
    if not gate_decision.should_retrieve:
        return []

    min_similarity = (
        PERSONAL_CUE_MIN_SIMILARITY
        if gate_decision.reason.startswith("personal_cue:")
        else MIN_SIMILARITY
    )

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
    return [r for r in rows if r.get("similarity", 0) >= min_similarity]


def _mi_prompt_label(row: dict) -> str:
    parts: list[str] = []

    category = row.get("category")
    structured_field = row.get("structured_field")
    confidence = row.get("confidence")
    retrieval_score = row.get("retrieval_score")

    if category:
        parts.append(str(category))
    if structured_field:
        parts.append(str(structured_field))
    if confidence is not None:
        parts.append(f"confidence={_mi_as_float(confidence, 0.0):.2f}")
    if retrieval_score is not None:
        parts.append(f"score={_mi_as_float(retrieval_score, 0.0):.2f}")

    return " | ".join(parts)


def _legacy_format_for_prompt_simple(memories: list[dict]) -> str:
    """Render retrieved memories into a system-prompt-ready string."""
    if not memories:
        return ""
    lines = ["What you know about the user from past conversations:"]
    for m in memories:
        lines.append(f"- {m['content']}")
    return "\n".join(lines)

# --- Memory Retrieval Ranking 2.0 (managed block) ---
# This block contains the active retrieval/prompt renderers.
# Earlier simple helpers are kept as _legacy_* for rollback/reference only.
# Goal: retrieve the right memories, ignore superseded memories, and prioritize
# structured/high-confidence memories without changing the database schema.

from datetime import datetime, timezone
from math import exp
from typing import Any


HIGH_PRIORITY_STRUCTURED_FIELDS = {
    "birthday": 0.20,
    "birthdate": 0.20,
    "timezone": 0.20,
    "preferred_name": 0.18,
    "nickname": 0.18,
    "assistant_name": 0.18,
    "daughter_name": 0.17,
    "child_name": 0.17,
    "spouse_name": 0.16,
    "location": 0.14,
}

CATEGORY_PRIORITY = {
    "identity": 0.18,
    "important_dates": 0.17,
    "preferences": 0.15,
    "constraints": 0.14,
    "relationships": 0.13,
    "goals": 0.12,
    "routines": 0.10,
    "projects": 0.10,
    "context": 0.05,
}

SOURCE_PRIORITY = {
    "user_correction": 0.10,
    "explicit_user_statement": 0.09,
    "user_answer_in_context": 0.08,
    "repeated_pattern": 0.04,
    "assistant_confirmation": -0.04,
}

KIND_PRIORITY = {
    "preference": 0.05,
    "fact": 0.04,
    "plan": 0.03,
    "context": 0.01,
}


def _mi_as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _mi_as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "1", "yes"}
    return bool(value)


def _mi_parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    raw = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _mi_age_days(row: dict) -> float | None:
    created = _mi_parse_dt(row.get("last_confirmed_at") or row.get("created_at"))
    if not created:
        return None
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)


def _mi_recency_score(row: dict) -> float:
    age = _mi_age_days(row)
    if age is None:
        return 0.0
    # Smooth decay: strong for recent context, but does not erase old identity facts.
    return 0.08 * exp(-age / 45.0)


def _mi_confidence_score(row: dict) -> float:
    # Legacy rows may not have confidence. Treat them as medium confidence, not zero.
    confidence = _mi_as_float(row.get("confidence"), 0.68)
    confidence = max(0.0, min(1.0, confidence))
    return 0.14 * confidence


def _mi_salience_score(row: dict) -> float:
    # Optional future column/metadata. Safe no-op if absent.
    salience = _mi_as_float(row.get("salience"), 0.0)
    if salience <= 0:
        return 0.0
    # Accept either 0..1 or 0..10.
    if salience > 1:
        salience = salience / 10.0
    return 0.10 * max(0.0, min(1.0, salience))


def _mi_metadata_priority(row: dict) -> float:
    category = str(row.get("category") or "").strip().lower()
    structured_field = str(row.get("structured_field") or "").strip().lower()
    source_priority = str(row.get("source_priority") or "").strip().lower()
    kind = str(row.get("kind") or "").strip().lower()

    return (
        CATEGORY_PRIORITY.get(category, 0.0)
        + HIGH_PRIORITY_STRUCTURED_FIELDS.get(structured_field, 0.0)
        + SOURCE_PRIORITY.get(source_priority, 0.0)
        + _mi_memory_governance_trust_bonus(row)
        + KIND_PRIORITY.get(kind, 0.0)
    )


def _mi_is_active_memory(row: dict) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status in {"archived", "superseded", "deleted"}:
        return False
    if row.get("deleted_at"):
        return False
    if _mi_as_bool(row.get("archived")):
        return False
    return not _mi_as_bool(row.get("superseded"))


def _mi_memory_governance_trust_bonus(row: dict) -> float:
    """Small invisible ranking lift for memories the system can trust more.

    This is not a user-facing review inbox. It simply makes confirmed/manual
    memories win close retrieval ties while high-confidence auto memories remain
    usable immediately.
    """
    if not _mi_is_active_memory(row):
        return -10.0

    source = str(row.get("source") or "").strip().lower()
    source_priority = str(row.get("source_priority") or "").strip().lower()
    confidence = _mi_as_float(row.get("confidence"), 0.0)

    if source in {"manual", "manual_review"}:
        return 0.060
    if row.get("last_confirmed_at"):
        return 0.045
    if (
        source == "auto"
        and confidence >= 0.90
        and source_priority in {"explicit_user_statement", "user_correction"}
    ):
        return 0.020
    return 0.0


def _mi_similarity_score(row: dict) -> float:
    similarity = _mi_as_float(row.get("similarity"), 0.0)
    similarity = max(0.0, min(1.0, similarity))
    # Similarity remains the primary signal.
    return similarity


def memory_retrieval_score(row: dict) -> float:
    if not _mi_is_active_memory(row):
        return -999.0

    score = (
        _mi_similarity_score(row)
        + _mi_confidence_score(row)
        + _mi_metadata_priority(row)
        + _mi_recency_score(row)
        + _mi_salience_score(row)
        + _mi_memory_governance_trust_bonus(row)
    )

    return round(score, 6)


def rank_memory_rows(rows: list[dict], *, min_similarity: float = MIN_SIMILARITY) -> list[dict]:
    scored: list[dict] = []

    for row in rows:
        if not _mi_is_active_memory(row):
            continue
        if _mi_similarity_score(row) < min_similarity:
            continue

        enriched = dict(row)
        enriched["retrieval_score"] = memory_retrieval_score(row)
        scored.append(enriched)

    # Trust/confidence/recency must win close ties before lightweight dedupe.
    scored.sort(
        key=lambda r: (
            _mi_as_float(r.get("retrieval_score"), 0.0),
            _mi_as_float(r.get("similarity"), 0.0),
            _mi_as_float(r.get("confidence"), 0.0),
            str(r.get("last_confirmed_at") or ""),
            str(r.get("created_at") or ""),
        ),
        reverse=True,
    )

    ranked: list[dict] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for row in scored:
        content_key = str(row.get("content") or "").strip().lower()
        field_key = str(row.get("structured_field") or "").strip().lower()
        value_key = str(row.get("structured_value") or "").strip().lower()
        key = (field_key, value_key, content_key)

        if key in seen_keys:
            continue

        seen_keys.add(key)
        ranked.append(row)

    return ranked
async def retrieve_relevant(user_id: str, query_text: str, limit: int = 8) -> list[dict]:
    """Find and rank memories relevant to the current user message.

    Ranking combines semantic similarity, confidence, structured-field/category
    priority, source priority, recency, and optional salience. Superseded rows are
    excluded both by SQL RPC when available and again in Python for safety.
    """

    from app.services.memory_query_normalizer import normalize_memory_query
    from app.services.memory_retrieval_gate import should_retrieve_memory

    gate_decision = should_retrieve_memory(query_text)
    if not gate_decision.should_retrieve:
        return []

    min_similarity = (
        PERSONAL_CUE_MIN_SIMILARITY
        if gate_decision.reason.startswith("personal_cue:")
        else MIN_SIMILARITY
    )

    normalized_query = normalize_memory_query(query_text, gate_decision=gate_decision)
    retrieval_query = normalized_query.query

    try:
        query_embedding = await embed_query(retrieval_query)
    except Exception as exc:  # noqa: BLE001
        log.warning("memory retrieval: embed failed: %s", exc)
        return []

    supabase = get_supabase()
    # Ask for more candidates than final limit so reranking has room to work.
    match_count = min(max(limit * 4, limit), 32)
    result = supabase.rpc(
        "match_memories",
        {
            "p_user_id": user_id,
            "p_query_embedding": query_embedding,
            "p_match_count": match_count,
        },
    ).execute()

    rows = result.data or []
    ranked = rank_memory_rows(rows, min_similarity=min_similarity)
    return ranked[:limit]


def format_for_prompt(memories: list[dict]) -> str:
    """Render retrieved memories into a system-prompt-ready string."""
    ranked = rank_memory_rows(memories)
    if not ranked:
        return ""

    lines = [
        "What you know about the user from past conversations:",
        "Use higher-confidence and structured memories first. Ignore any archived/superseded memories.",
    ]
    for m in ranked:
        label = _mi_prompt_label(m)
        lines.append(f"- {m['content']}{label}")
    return "\n".join(lines)



def _mi_safe_join(values: set[str], *, limit: int = 8) -> str:
    cleaned = sorted(v for v in values if v)
    if not cleaned:
        return "-"
    shown = cleaned[:limit]
    suffix = f"+{len(cleaned) - limit}" if len(cleaned) > limit else ""
    return ",".join(shown) + suffix


def build_retrieval_diagnostics(
    memories: list[dict],
    related_summaries: list[dict] | None = None,
) -> str:
    """Return safe memory-context diagnostics for logs.

    This intentionally does NOT include memory content, evidence, summary text,
    titles, or user-provided values. It only exposes aggregate counts and
    metadata useful for debugging whether retrieval/injection happened.
    """
    summaries = related_summaries or []
    categories = {
        str(m.get("category") or "").strip().lower()
        for m in memories
        if m.get("category")
    }
    fields = {
        str(m.get("structured_field") or "").strip().lower()
        for m in memories
        if m.get("structured_field")
    }

    memory_scores: list[float] = []
    for m in memories:
        if m.get("retrieval_score") is not None:
            memory_scores.append(_mi_as_float(m.get("retrieval_score"), 0.0))
        elif m.get("similarity") is not None:
            memory_scores.append(_mi_as_float(m.get("similarity"), 0.0))

    summary_scores: list[float] = []
    for s in summaries:
        if s.get("similarity") is not None:
            summary_scores.append(_mi_as_float(s.get("similarity"), 0.0))

    avg_memory_score = (
        f"{sum(memory_scores) / len(memory_scores):.3f}" if memory_scores else "-"
    )
    max_memory_score = f"{max(memory_scores):.3f}" if memory_scores else "-"
    avg_summary_score = (
        f"{sum(summary_scores) / len(summary_scores):.3f}" if summary_scores else "-"
    )

    return (
        "memory_context:"
        f" memories={len(memories)}"
        f" summaries={len(summaries)}"
        f" categories={_mi_safe_join(categories)}"
        f" fields={_mi_safe_join(fields)}"
        f" avg_memory_score={avg_memory_score}"
        f" max_memory_score={max_memory_score}"
        f" avg_summary_score={avg_summary_score}"
    )


# --- End Memory Retrieval Ranking 2.0 ---
