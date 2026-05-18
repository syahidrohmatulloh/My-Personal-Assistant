"""Safe resolve actions for Memory Quality Layer v1.

v1 intentionally supports only safe data hygiene actions:
- keep one memory and archive the rest
- archive selected memory/memories

No automatic merge/rewrite in v1.
"""

from __future__ import annotations

from dataclasses import dataclass


VALID_ACTIONS = {"keep_one_archive_rest", "archive_memory"}


@dataclass(frozen=True)
class QualityResolvePlan:
    action: str
    keep_memory_id: str | None
    archive_memory_ids: list[str]
    all_memory_ids: list[str]


def build_quality_resolve_plan(
    *,
    action: str,
    keep_memory_id: str | None,
    archive_memory_ids: list[str] | None,
) -> QualityResolvePlan:
    cleaned_action = (action or "").strip()
    archive_ids = _dedupe_ids(archive_memory_ids or [])
    keep_id = _clean_id(keep_memory_id)

    if cleaned_action not in VALID_ACTIONS:
        raise ValueError("Unsupported resolve action")

    if cleaned_action == "keep_one_archive_rest":
        if not keep_id:
            raise ValueError("keep_memory_id is required")
        if not archive_ids:
            raise ValueError("archive_memory_ids is required")
        if keep_id in archive_ids:
            raise ValueError("keep_memory_id cannot also be archived")

        all_ids = _dedupe_ids([keep_id, *archive_ids])
        return QualityResolvePlan(
            action=cleaned_action,
            keep_memory_id=keep_id,
            archive_memory_ids=archive_ids,
            all_memory_ids=all_ids,
        )

    if cleaned_action == "archive_memory":
        if not archive_ids:
            raise ValueError("archive_memory_ids is required")

        return QualityResolvePlan(
            action=cleaned_action,
            keep_memory_id=None,
            archive_memory_ids=archive_ids,
            all_memory_ids=archive_ids,
        )

    raise ValueError("Unsupported resolve action")


def _dedupe_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for value in values:
        cleaned = _clean_id(value)
        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        out.append(cleaned)

    return out


def _clean_id(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None
