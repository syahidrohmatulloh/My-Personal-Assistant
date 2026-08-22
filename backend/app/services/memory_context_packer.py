"""Pack retrieved memory context before injecting it into the LLM prompt.

Retrieval decides what is relevant. This packer decides what is safe, compact,
and useful enough to place into the prompt for a single turn.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


MAX_MEMORY_PROMPT_ITEMS = 5
MAX_RELATED_SUMMARY_ITEMS = 2
MAX_MEMORY_ITEMS_PER_CATEGORY = 4
MAX_MEMORY_ITEM_CHARS = 280
MAX_SUMMARY_ITEM_CHARS = 360
MAX_PACKED_CONTEXT_CHARS = 2200

_UNCAPPED_CATEGORIES = {
    "identity",
    "important_dates",
    "relationships",
    "constraints",
}

_CATEGORY_PACKING_BONUS = {
    "identity": 0.60,
    "important_dates": 0.50,
    "relationships": 0.40,
    "constraints": 0.35,
    "preferences": 0.10,
    "routines": 0.05,
    "goals": 0.05,
}


@dataclass(frozen=True)
class PackedMemoryContext:
    text: str
    memory_count: int
    summary_count: int
    dropped_memory_count: int
    dropped_summary_count: int
    total_chars: int = 0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate_text(text: str, max_chars: int) -> str:
    text = _as_text(text)
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "…"


def _is_active_memory(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "active").strip().lower()
    if status in {"archived", "superseded", "deleted"}:
        return False
    if row.get("deleted_at"):
        return False
    if bool(row.get("archived")) or bool(row.get("superseded")):
        return False
    return True


def _memory_score(row: dict[str, Any]) -> float:
    retrieval_score = row.get("retrieval_score")
    if retrieval_score is not None:
        return _as_float(retrieval_score)
    similarity = row.get("similarity")
    if similarity is not None:
        return _as_float(similarity)
    return _as_float(row.get("confidence"))


def _packing_score(row: dict[str, Any]) -> float:
    category = _as_text(row.get("category")).casefold()
    structured_field = _as_text(row.get("structured_field"))
    structured_bonus = 0.12 if structured_field else 0.0
    return _memory_score(row) + _CATEGORY_PACKING_BONUS.get(category, 0.0) + structured_bonus


def _memory_tie_breaker(row: dict[str, Any]) -> float:
    return _as_float(row.get("confidence"))


def _memory_label(row: dict[str, Any]) -> str:
    parts: list[str] = []

    category = _as_text(row.get("category"))
    structured_field = _as_text(row.get("structured_field"))
    confidence = row.get("confidence")
    retrieval_score = row.get("retrieval_score")

    if category:
        parts.append(category)
    if structured_field:
        parts.append(structured_field)
    if confidence is not None:
        parts.append(f"confidence={_as_float(confidence):.2f}")
    if retrieval_score is not None:
        parts.append(f"score={_as_float(retrieval_score):.2f}")

    return f" ({' | '.join(parts)})" if parts else ""


def _select_memory_rows(
    memories: list[dict[str, Any]],
    *,
    max_items: int,
    max_per_category: int,
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, dict[str, Any]]] = []

    for index, row in enumerate(memories):
        if not isinstance(row, dict):
            continue
        content = _as_text(row.get("content"))
        if not content:
            continue
        if not _is_active_memory(row):
            continue
        candidates.append((index, row))

    candidates.sort(
        key=lambda item: (
            _packing_score(item[1]),
            _memory_score(item[1]),
            _memory_tie_breaker(item[1]),
            -item[0],
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    category_counts: dict[str, int] = defaultdict(int)

    for _index, row in candidates:
        content = _as_text(row.get("content"))
        content_key = content.casefold()
        if content_key in seen_content:
            continue

        category = _as_text(row.get("category")).casefold() or "uncategorized"
        if (
            category not in _UNCAPPED_CATEGORIES
            and category_counts[category] >= max_per_category
        ):
            continue

        selected.append(row)
        seen_content.add(content_key)
        category_counts[category] += 1

        if len(selected) >= max_items:
            break

    return selected


def _select_summary_rows(
    summaries: list[dict[str, Any]],
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in summaries:
        if not isinstance(row, dict):
            continue

        summary = _as_text(row.get("summary"))
        if not summary:
            continue

        title = _as_text(row.get("title")) or "Untitled"
        key = f"{title}\n{summary}".casefold()
        if key in seen:
            continue

        selected.append(row)
        seen.add(key)

        if len(selected) >= max_items:
            break

    return selected


def _render_memory_section(
    rows: list[dict[str, Any]],
    *,
    max_chars: int,
    max_item_chars: int,
) -> tuple[str, int]:
    if not rows or max_chars <= 0:
        return "", 0

    header = [
        "## Relevant memory context",
        "Use this silently for continuity. Do not recite it unless directly useful.",
    ]
    lines: list[str] = []

    for row in rows:
        line = f"- {_truncate_text(_as_text(row.get('content')), max_item_chars)}{_memory_label(row)}"
        candidate = "\n".join(header + lines + [line])
        if len(candidate) > max_chars:
            break
        lines.append(line)

    if not lines:
        return "", 0

    return "\n".join(header + lines), len(lines)


def _render_summary_section(
    rows: list[dict[str, Any]],
    *,
    max_chars: int,
    max_item_chars: int,
) -> tuple[str, int]:
    if not rows or max_chars <= 0:
        return "", 0

    header = [
        "## Possibly related past conversations",
        "Use for grounding only; do not recap unless the user asks.",
    ]
    lines: list[str] = []

    for row in rows:
        when = _as_text(row.get("updated_at"))[:10] if row.get("updated_at") else "?"
        title = _truncate_text(_as_text(row.get("title")) or "Untitled", 120)
        summary = _truncate_text(_as_text(row.get("summary")), max_item_chars)
        line = f"- [{when}] {title}: {summary}"
        candidate = "\n".join(header + lines + [line])
        if len(candidate) > max_chars:
            break
        lines.append(line)

    if not lines:
        return "", 0

    return "\n".join(header + lines), len(lines)


def pack_memory_context_for_prompt(
    *,
    legacy_memories: list[dict[str, Any]] | None,
    related_summaries: list[dict[str, Any]] | None,
    max_memory_items: int = MAX_MEMORY_PROMPT_ITEMS,
    max_related_summary_items: int = MAX_RELATED_SUMMARY_ITEMS,
    max_memory_items_per_category: int = MAX_MEMORY_ITEMS_PER_CATEGORY,
    max_memory_item_chars: int = MAX_MEMORY_ITEM_CHARS,
    max_summary_item_chars: int = MAX_SUMMARY_ITEM_CHARS,
    max_total_chars: int = MAX_PACKED_CONTEXT_CHARS,
) -> PackedMemoryContext:
    memories = list(legacy_memories or [])
    summaries = list(related_summaries or [])

    selected_memories = _select_memory_rows(
        memories,
        max_items=max_memory_items,
        max_per_category=max_memory_items_per_category,
    )
    selected_summaries = _select_summary_rows(
        summaries,
        max_items=max_related_summary_items,
    )

    sections: list[str] = []
    remaining_chars = max_total_chars

    memory_section, rendered_memory_count = _render_memory_section(
        selected_memories,
        max_chars=remaining_chars,
        max_item_chars=max_memory_item_chars,
    )
    if memory_section:
        sections.append(memory_section)
        remaining_chars = max(0, remaining_chars - len(memory_section) - 2)

    summary_section, rendered_summary_count = _render_summary_section(
        selected_summaries,
        max_chars=remaining_chars,
        max_item_chars=max_summary_item_chars,
    )
    if summary_section:
        sections.append(summary_section)

    text = "\n\n".join(sections)

    return PackedMemoryContext(
        text=text,
        memory_count=rendered_memory_count,
        summary_count=rendered_summary_count,
        dropped_memory_count=max(0, len(memories) - rendered_memory_count),
        dropped_summary_count=max(0, len(summaries) - rendered_summary_count),
        total_chars=len(text),
    )
