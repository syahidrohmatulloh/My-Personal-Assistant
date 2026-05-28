"""Memory Quality Layer v1.

Read-only quality audit for long-term memories.

Goals:
- detect likely duplicates
- detect likely conflicts
- detect low-quality memories
- produce a review queue

This module is deterministic and conservative. It does not mutate memories and
does not call an LLM.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.memory_user_facing_safety import memory_low_quality_reasons


DUPLICATE_SIMILARITY_THRESHOLD = 0.78

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "this",
    "to",
    "user",
    "with",
    "you",
    "aku",
    "dan",
    "di",
    "ini",
    "itu",
    "ke",
    "saya",
    "yang",
}


CONFLICT_FIELDS = {
    "assistant_name",
    "avoid_calling_user",
    "birthday",
    "communication_preference",
    "general_preference",
    "preferred_name",
    "timezone",
    "ui_preference",
}


LOW_VALUE_FIELDS = {
    "",
    "unknown",
    "none",
    "null",
    "n/a",
}

def stale_after_days() -> int:
    raw = os.getenv("MEMORY_FRESHNESS_STALE_DAYS", "120")
    try:
        value = int(raw)
    except ValueError:
        value = 120

    return max(value, 30)



@dataclass(frozen=True)
class MemoryQualityIssue:
    issue_type: str
    severity: str
    memory_ids: list[str]
    title: str
    explanation: str
    suggested_action: str
    reason: dict[str, Any]
    memories: list[dict[str, Any]]


def assess_memory_quality(memories: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess memory quality and return a UI-friendly review payload."""
    active = [_normalize_memory(row) for row in memories if _is_active(row)]

    duplicate_groups = _find_duplicate_groups(active)
    conflict_groups = _find_conflict_groups(active)
    low_quality = _find_low_quality_memories(active)
    stale_memories = _find_stale_memories(active)

    issues: list[MemoryQualityIssue] = []
    issues.extend(_duplicate_issues(duplicate_groups))
    issues.extend(_conflict_issues(conflict_groups))
    issues.extend(_low_quality_issues(low_quality))
    issues.extend(_stale_issues(stale_memories))

    return {
        "summary": {
            "active_memories": len(active),
            "duplicate_groups": len(duplicate_groups),
            "conflict_groups": len(conflict_groups),
            "low_quality_memories": len(low_quality),
            "stale_memories": len(stale_memories),
            "needs_review": len(issues),
        },
        "duplicate_groups": duplicate_groups,
        "conflict_groups": conflict_groups,
        "low_quality_memories": low_quality,
        "stale_memories": stale_memories,
        "review_items": [_issue_to_dict(issue) for issue in issues],
    }


def _normalize_memory(row: dict[str, Any]) -> dict[str, Any]:
    content = _compact(row.get("content") or "")
    category = _compact(row.get("category") or row.get("kind") or "other").lower()
    structured_field = _normalize_key(row.get("structured_field"))
    structured_value = _compact(row.get("structured_value") or "")

    return {
        **row,
        "id": str(row.get("id") or ""),
        "content": content,
        "category": category or "other",
        "structured_field": structured_field,
        "structured_value": structured_value,
        "_norm_content": _normalize_text(content),
        "_tokens": _tokens(content),
        "_norm_value": _normalize_text(structured_value),
    }


def _is_active(row: dict[str, Any]) -> bool:
    if row.get("superseded") is True:
        return False

    if row.get("archived") is True:
        return False

    if row.get("status") in {"archived", "superseded", "deleted"}:
        return False

    if row.get("deleted_at"):
        return False

    return True


def _find_duplicate_groups(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    used: set[str] = set()

    for i, left in enumerate(memories):
        left_id = left["id"]
        if not left_id or left_id in used:
            continue

        group = [left]

        for right in memories[i + 1 :]:
            right_id = right["id"]
            if not right_id or right_id in used:
                continue

            if _are_duplicates(left, right):
                group.append(right)

        if len(group) > 1:
            for item in group:
                used.add(item["id"])
            groups.append(group)

    return [_group_payload("duplicate", group) for group in groups]


def _are_duplicates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    # Strongest signal: same structured fact.
    if (
        left["structured_field"]
        and left["structured_field"] != "manual_memory"
        and left["structured_field"] == right["structured_field"]
        and left["_norm_value"]
        and left["_norm_value"] == right["_norm_value"]
    ):
        return True

    # Same category/field and highly similar content.
    if left["category"] == right["category"] and left["structured_field"] == right["structured_field"]:
        return _jaccard(left["_tokens"], right["_tokens"]) >= DUPLICATE_SIMILARITY_THRESHOLD

    # Fallback: very similar content regardless of field.
    return _jaccard(left["_tokens"], right["_tokens"]) >= 0.9


def _find_conflict_groups(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for memory in memories:
        field = memory["structured_field"]
        if not field or field == "manual_memory":
            continue

        if field not in CONFLICT_FIELDS:
            continue

        key = (memory["category"], field)
        buckets.setdefault(key, []).append(memory)

    conflict_groups: list[dict[str, Any]] = []

    for (_category, _field), items in buckets.items():
        values = {item["_norm_value"] for item in items if item["_norm_value"]}
        if len(values) <= 1:
            continue

        conflict_groups.append(_group_payload("conflict", items))

    return conflict_groups


def _find_low_quality_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    low_quality: list[dict[str, Any]] = []

    for memory in memories:
        content = memory["content"]
        field = memory["structured_field"]
        value = memory["structured_value"]
        norm_value = memory["_norm_value"]

        reasons: list[str] = []

        if len(content) < 8:
            reasons.append("Too short to be useful")

        if field in LOW_VALUE_FIELDS:
            reasons.append("Missing memory key")

        if not norm_value or norm_value in LOW_VALUE_FIELDS:
            reasons.append("Missing memory value")

        if field == "manual_memory" and len(memory["_tokens"]) < 3:
            reasons.append("Needs more detail")

        if _looks_like_debug_or_raw_metadata(content):
            reasons.append("Looks technical or raw")

        for reason in memory_low_quality_reasons(
            content=content,
            structured_field=field,
            structured_value=value,
        ):
            if reason not in reasons:
                reasons.append(reason)

        if reasons:
            low_quality.append(
                {
                    "id": memory["id"],
                    "content": memory["content"],
                    "category": memory["category"],
                    "structured_field": memory["structured_field"],
                    "structured_value": memory["structured_value"],
                    "reasons": reasons,
                }
            )

    return low_quality


def _find_stale_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    threshold = stale_after_days()
    now = datetime.now(timezone.utc)
    stale: list[dict[str, Any]] = []

    for memory in memories:
        age_days = _memory_age_days(memory, now)
        if age_days is None or age_days < threshold:
            continue

        stale.append(
            {
                "id": memory["id"],
                "content": memory["content"],
                "category": memory["category"],
                "structured_field": memory["structured_field"],
                "structured_value": memory["structured_value"],
                "days_since_confirmation": age_days,
                "threshold_days": threshold,
            }
        )

    return stale


def _memory_age_days(memory: dict[str, Any], now: datetime) -> int | None:
    timestamp = (
        memory.get("last_confirmed_at")
        or memory.get("updated_at")
        or memory.get("created_at")
    )

    dt = _parse_datetime(timestamp)
    if not dt:
        return None

    return max(0, (now - dt).days)


def _parse_datetime(value: Any) -> datetime | None:
    raw = _compact(value)
    if not raw:
        return None

    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _duplicate_issues(groups: list[dict[str, Any]]) -> list[MemoryQualityIssue]:
    return [
        MemoryQualityIssue(
            issue_type="duplicate",
            severity="medium",
            memory_ids=group["memory_ids"],
            title="Possible duplicate memories",
            explanation="These memories look very similar and may be archived safely.",
            suggested_action="Keep the clearest memory and archive the others.",
            reason=_duplicate_reason(group),
            memories=group["memories"],
        )
        for group in groups
    ]


def _conflict_issues(groups: list[dict[str, Any]]) -> list[MemoryQualityIssue]:
    return [
        MemoryQualityIssue(
            issue_type="conflict",
            severity="high",
            memory_ids=group["memory_ids"],
            title="Possible conflicting memories",
            explanation="These memories describe the same kind of fact but have different values.",
            suggested_action="Keep the version that is still true and archive the others.",
            reason=_conflict_reason(group),
            memories=group["memories"],
        )
        for group in groups
    ]


def _low_quality_issues(items: list[dict[str, Any]]) -> list[MemoryQualityIssue]:
    return [
        MemoryQualityIssue(
            issue_type="low_quality",
            severity="low",
            memory_ids=[item["id"]],
            title="Memory may need more detail",
            explanation=", ".join(item["reasons"]),
            suggested_action="Edit the memory to make it clearer, or archive it.",
            reason=_low_quality_reason(item),
            memories=[_issue_memory_payload(item)],
        )
        for item in items
    ]


def _group_payload(group_type: str, group: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": group_type,
        "memory_ids": [item["id"] for item in group],
        "memories": [
            {
                "id": item["id"],
                "content": item["content"],
                "category": item["category"],
                "structured_field": item["structured_field"],
                "structured_value": item["structured_value"],
            }
            for item in group
        ],
    }


def _duplicate_reason(group: dict[str, Any]) -> dict[str, Any]:
    memories = group.get("memories") or []
    fields = _unique_non_empty(memory.get("structured_field") for memory in memories)
    values = _unique_non_empty(memory.get("structured_value") for memory in memories)

    if len(fields) == 1 and len(values) == 1:
        return {
            "main": "These memories use the same memory key and store the same detail.",
            "field": fields[0],
            "values": values,
        }

    if len(fields) == 1:
        return {
            "main": "These memories use the same memory key and have very similar wording.",
            "field": fields[0],
            "values": values,
        }

    return {
        "main": "These memories have very similar wording and may describe the same thing.",
        "field": None,
        "values": values,
    }


def _conflict_reason(group: dict[str, Any]) -> dict[str, Any]:
    memories = group.get("memories") or []
    fields = _unique_non_empty(memory.get("structured_field") for memory in memories)
    values = _unique_non_empty(memory.get("structured_value") for memory in memories)

    return {
        "main": "These memories use the same memory key but store different details.",
        "field": fields[0] if len(fields) == 1 else None,
        "values": values,
    }


def _low_quality_reason(item: dict[str, Any]) -> dict[str, Any]:
    reasons = item.get("reasons") or []

    return {
        "main": "This memory may not be clear enough to be useful later.",
        "field": item.get("structured_field"),
        "values": [item.get("structured_value")] if item.get("structured_value") else [],
        "reasons": reasons,
    }


def _unique_non_empty(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for value in values:
        cleaned = _compact(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)

    return out


def _stale_issues(items: list[dict[str, Any]]) -> list[MemoryQualityIssue]:
    return [
        MemoryQualityIssue(
            issue_type="stale_memory",
            severity="low",
            memory_ids=[item["id"]],
            title="Memory may need confirmation",
            explanation=(
                f"This memory has not been confirmed for "
                f"{item['days_since_confirmation']} days."
            ),
            suggested_action="Confirm it is still true, edit it, or archive it.",
            reason={
                "main": (
                    f"This memory has not been confirmed for "
                    f"{item['days_since_confirmation']} days. It may still be true, "
                    "but should be checked."
                ),
                "field": item.get("structured_field"),
                "values": [item.get("structured_value")] if item.get("structured_value") else [],
                "days_since_confirmation": item["days_since_confirmation"],
                "threshold_days": item["threshold_days"],
            },
            memories=[_issue_memory_payload(item)],
        )
        for item in items
    ]


def _issue_to_dict(issue: MemoryQualityIssue) -> dict[str, Any]:
    return {
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "memory_ids": issue.memory_ids,
        "title": issue.title,
        "explanation": issue.explanation,
        "suggested_action": issue.suggested_action,
        "reason": issue.reason,
        "memories": issue.memories,
    }


def _issue_memory_payload(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": memory.get("id"),
        "content": memory.get("content"),
        "category": memory.get("category"),
        "structured_field": memory.get("structured_field"),
        "structured_value": memory.get("structured_value"),
    }


def _looks_like_debug_or_raw_metadata(content: str) -> bool:
    low = content.lower()
    suspicious = [
        "traceback",
        "undefined is not",
        "null pointer",
        "uuid",
        "source_priority",
        "structured_field",
        "structured_value",
        "console.log",
        "stack trace",
        "due_date=",
        "start_at=",
        "end_at=",
        "goal_id=",
        "polished_theme",
        "aware_glass",
        "mobile_smooth",
        "consistent_personal",
    ]
    return any(term in low for term in suspicious)


def _normalize_key(value: Any) -> str:
    raw = _compact(value or "").lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return raw


def _normalize_text(value: str) -> str:
    value = _compact(value).lower()
    value = re.sub(r"[^a-z0-9\s/_+-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokens(value: str) -> set[str]:
    normalized = _normalize_text(value)
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0

    return len(left & right) / len(left | right)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())
