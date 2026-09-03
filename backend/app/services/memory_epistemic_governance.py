"""Canonical deterministic epistemic governance for durable memory.

M35c2c separates storage provenance from current-writer provenance.

`legacy_unknown` is intentionally storage/audit-only. New extraction
writers must never assign it. It means the historical row survived,
but its original evidence path can no longer be reconstructed safely.

Invariants:

Insertion != Confirmation
Repetition != Confirmation
Inference != Truth
Projection match != Evidence strength
Unknown provenance != Explicit user statement
"""

from __future__ import annotations

from typing import Any


LEGACY_UNKNOWN_PRIORITY = "legacy_unknown"
SYSTEM_INFERENCE_PRIORITY = "system_inference"
ASSISTANT_CONFIRMATION_PRIORITY = "assistant_confirmation"

MAX_UNVERIFIED_CONFIDENCE = 0.54

CANONICAL_STORED_PRIORITIES = frozenset(
    {
        "explicit_user_statement",
        "user_answer_in_context",
        "user_correction",
        "repeated_pattern",
        ASSISTANT_CONFIRMATION_PRIORITY,
        SYSTEM_INFERENCE_PRIORITY,
        LEGACY_UNKNOWN_PRIORITY,
    }
)

# These provenance classes are not sufficient by themselves to establish
# a durable fact as verified. A later real confirmation timestamp may
# still establish confirmation when full lifecycle metadata is available.
UNVERIFIED_PROVENANCE = frozenset(
    {
        ASSISTANT_CONFIRMATION_PRIORITY,
        SYSTEM_INFERENCE_PRIORITY,
        LEGACY_UNKNOWN_PRIORITY,
    }
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def source_priority(row: dict[str, Any]) -> str:
    return _text(row.get("source_priority"))


def has_confirmation(row: dict[str, Any]) -> bool:
    return bool(row.get("last_confirmed_at"))


def provenance_requires_confirmation(
    row: dict[str, Any],
) -> bool:
    """Return whether provenance alone requires verification.

    Missing provenance from an automatic writer is also non-authoritative.
    This protects future legacy/null rows even after the historical corpus
    has been repaired.
    """
    priority = source_priority(row)

    if priority in UNVERIFIED_PROVENANCE:
        return True

    source = _text(row.get("source"))
    if source == "auto" and not priority:
        return True

    return False


def effective_confidence(
    row: dict[str, Any],
    *,
    default: float = 0.68,
) -> float:
    """Confidence usable by retrieval/ranking policy.

    Historical/raw confidence is preserved for audit except where an
    exact deterministic inference is repaired in the migration.

    Unverified provenance cannot obtain ranking authority above the
    M35 conservative inference ceiling unless a real confirmation
    timestamp is available on the row.
    """
    confidence = max(
        0.0,
        min(
            1.0,
            _float(
                row.get("confidence"),
                default,
            ),
        ),
    )

    if (
        provenance_requires_confirmation(row)
        and not has_confirmation(row)
    ):
        return min(
            confidence,
            MAX_UNVERIFIED_CONFIDENCE,
        )

    return confidence
