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

import re
from dataclasses import dataclass
from typing import Any


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


@dataclass(frozen=True)
class MemoryQualityIssue:
    issue_type: str
    severity: str
    memory_ids: list[str]
    title: str
    explanation: str
    suggested_action: str


def assess_memory_quality(memories: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess memory quality and return a UI-friendly review payload."""
    active = [_normalize_memory(row) for row in memories if _is_active(row)]

    duplicate_groups = _find_duplicate_groups(active)
    conflict_groups = _find_conflict_groups(active)
    low_quality = _find_low_quality_memories(active)

    issues: list[MemoryQualityIssue] = []
    issues.extend(_duplicate_issues(duplicate_groups))
    issues.extend(_conflict_issues(conflict_groups))
    issues.extend(_low_quality_issues(low_quality))

    return {
        "summary": {
            "active_memories": len(active),
            "duplicate_groups": len(duplicate_groups),
            "conflict_groups": len(conflict_groups),
            "low_quality_memories": len(low_quality),
            "needs_review": len(issues),
        },
        "duplicate_groups": duplicate_groups,
        "conflict_groups": conflict_groups,
        "low_quality_memories": low_quality,
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


def _duplicate_issues(groups: list[dict[str, Any]]) -> list[MemoryQualityIssue]:
    return [
        MemoryQualityIssue(
            issue_type="duplicate",
            severity="medium",
            memory_ids=group["memory_ids"],
            title="Possible duplicate memories",
            explanation="These memories look very similar and may be merged or archived.",
            suggested_action="Review and keep the clearest memory.",
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
            suggested_action="Ask the user which one is still true.",
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


def _issue_to_dict(issue: MemoryQualityIssue) -> dict[str, Any]:
    return {
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "memory_ids": issue.memory_ids,
        "title": issue.title,
        "explanation": issue.explanation,
        "suggested_action": issue.suggested_action,
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
