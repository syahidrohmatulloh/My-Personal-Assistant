"""Memory Hygiene Gate.

This module prevents low-value, accidental, or ambiguous chat fragments from
becoming durable memories.

It is intentionally generic:
- no user-specific hardcoding
- no assistant-name hardcoding
- no project-specific facts
- only universal memory-quality rules

The AI extractor should provide structured_field and structured_value. The
hygiene gate is a final safety layer before insertion.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


EXPLICIT_MEMORY_PATTERNS = (
    r"\bremember that\b",
    r"\bremember this\b",
    r"\bsave this\b",
    r"\bnote that\b",
    r"\bcatat\b",
    r"\bingat bahwa\b",
    r"\btolong ingat\b",
    r"\bsimpan ini\b",
)

TRIVIAL_EXACT_PHRASES = {
    "hi",
    "hai",
    "hey",
    "hello",
    "halo",
    "hallo",
    "pagi",
    "siang",
    "sore",
    "malam",
    "good morning",
    "good night",
    "ok",
    "oke",
    "okay",
    "sip",
    "siap",
    "yes",
    "no",
    "ya",
    "iya",
    "y",
    "nope",
    "done",
    "lanjut",
    "next",
    "test",
    "testing",
    "coba",
    "tes",
    "makasih",
    "thanks",
    "thank you",
    "noted",
    "noted thanks",
}

LOW_VALUE_PATTERNS = (
    r"^[\W_]+$",
    r"^(ha)+$",
    r"^(wkwk)+$",
    r"^(hehe)+$",
)


@dataclass(frozen=True)
class MemoryHygieneResult:
    should_store: bool
    reason: str
    content: str
    structured_field: str | None
    structured_value: str | None
    category: str | None
    confidence: float


def evaluate_memory_candidate(
    *,
    content: str | None,
    structured_field: str | None = None,
    structured_value: str | None = None,
    category: str | None = None,
    confidence: float | None = None,
    source_priority: str | None = None,
) -> MemoryHygieneResult:
    cleaned = _clean_text(content)
    field = _clean_optional(structured_field)
    value = _clean_optional(structured_value)
    cat = _clean_optional(category)
    conf = _safe_confidence(confidence)

    explicit = _has_explicit_memory_intent(cleaned)
    normalized = _normalize(cleaned)
    token_count = len(_tokens(cleaned))

    if not cleaned:
        return _reject("empty_content", cleaned, field, value, cat, conf)

    if not explicit and _is_trivial_exact(normalized):
        return _reject("trivial_chat_fragment", cleaned, field, value, cat, conf)

    if not explicit and _matches_low_value_pattern(normalized):
        return _reject("low_value_pattern", cleaned, field, value, cat, conf)

    if not explicit and token_count <= 1:
        return _reject("too_short_without_explicit_memory_intent", cleaned, field, value, cat, conf)

    inferred_field, inferred_value = _infer_key_value(cleaned, field, value)

    if not inferred_field or not inferred_value:
        if explicit and token_count >= 4:
            inferred_field = inferred_field or "explicit_memory"
            inferred_value = inferred_value or _strip_explicit_prefix(cleaned)
        else:
            return _reject("missing_memory_key_or_value", cleaned, inferred_field, inferred_value, cat, conf)

    if not explicit and token_count <= 2 and not _has_specific_signal(cleaned, inferred_value):
        return _reject("too_short_without_specific_signal", cleaned, inferred_field, inferred_value, cat, conf)

    if conf < 0.45 and not explicit:
        return _reject("low_confidence", cleaned, inferred_field, inferred_value, cat, conf)

    return MemoryHygieneResult(
        should_store=True,
        reason="accepted",
        content=cleaned,
        structured_field=inferred_field,
        structured_value=inferred_value,
        category=cat or _infer_category(inferred_field),
        confidence=conf,
    )


def sanitize_memory_row(row: dict[str, Any]) -> dict[str, Any] | None:
    result = evaluate_memory_candidate(
        content=row.get("content"),
        structured_field=row.get("structured_field") or row.get("memory_key"),
        structured_value=row.get("structured_value") or row.get("memory_value"),
        category=row.get("category"),
        confidence=row.get("confidence"),
        source_priority=row.get("source_priority"),
    )

    if not result.should_store:
        return None

    out = dict(row)
    out["content"] = result.content
    out["structured_field"] = result.structured_field
    out["structured_value"] = result.structured_value
    out["category"] = result.category
    out["confidence"] = result.confidence
    out.setdefault("hygiene_reason", result.reason)
    return out


def sanitize_memory_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for row in rows:
        clean = sanitize_memory_row(row)
        if clean is not None:
            sanitized.append(clean)
    return sanitized


def _reject(
    reason: str,
    content: str,
    field: str | None,
    value: str | None,
    category: str | None,
    confidence: float,
) -> MemoryHygieneResult:
    return MemoryHygieneResult(
        should_store=False,
        reason=reason,
        content=content,
        structured_field=field,
        structured_value=value,
        category=category,
        confidence=confidence,
    )


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _clean_optional(value: Any) -> str | None:
    cleaned = _clean_text(str(value or ""))
    if not cleaned:
        return None
    if cleaned.lower() in {"none", "null", "n/a", "unknown"}:
        return None
    return cleaned


def _normalize(value: str) -> str:
    lowered = value.casefold().strip()
    lowered = re.sub(r"[!?.。！？]+$", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _tokens(value: str) -> list[str]:
    return re.findall(r"[\w@.+:-]+", value.casefold())


def _safe_confidence(value: float | None) -> float:
    try:
        if value is None:
            return 0.72
        parsed = float(value)
    except Exception:
        return 0.72
    return max(0.0, min(1.0, parsed))


def _has_explicit_memory_intent(value: str) -> bool:
    normalized = _normalize(value)
    return any(re.search(pattern, normalized) for pattern in EXPLICIT_MEMORY_PATTERNS)


def _strip_explicit_prefix(value: str) -> str:
    stripped = value
    stripped = re.sub(
        r"(?i)^\s*(remember that|remember this|save this|note that|catat|ingat bahwa|tolong ingat|simpan ini)\s*[:,-]?\s*",
        "",
        stripped,
    )
    return _clean_text(stripped)


def _is_trivial_exact(normalized: str) -> bool:
    return normalized in TRIVIAL_EXACT_PHRASES


def _matches_low_value_pattern(normalized: str) -> bool:
    return any(re.fullmatch(pattern, normalized) for pattern in LOW_VALUE_PATTERNS)


def _has_specific_signal(content: str, value: str | None) -> bool:
    probe = f"{content} {value or ''}"
    return bool(
        re.search(r"\d", probe)
        or re.search(r"[@:/+-]", probe)
        or re.search(r"\b(gmt|utc|wib|wita|wit|jakarta|indonesia)\b", probe.casefold())
    )


def _infer_key_value(
    content: str,
    structured_field: str | None,
    structured_value: str | None,
) -> tuple[str | None, str | None]:
    if structured_field and structured_value:
        return structured_field, structured_value

    cleaned = _strip_explicit_prefix(content)
    lower = cleaned.casefold()

    patterns: tuple[tuple[str, str, str], ...] = (
        ("preference", r"\buser prefers\b\s+(.+)", "preference"),
        ("preference", r"\buser likes\b\s+(.+)", "preference"),
        ("preference", r"\buser dislikes\b\s+(.+)", "preference"),
        ("preference", r"\buser wants\b\s+(.+)", "preference"),
        ("preference", r"\bpanggil (aku|saya)\b\s+(.+)", "preferred_address"),
        ("preference", r"\bjangan panggil (aku|saya)\b\s+(.+)", "disallowed_address"),
        ("identity", r"\bmy name is\b\s+(.+)", "name"),
        ("identity", r"\bnama saya\b\s+(.+)", "name"),
        ("context", r"\bi live in\b\s+(.+)", "location"),
        ("context", r"\bsaya tinggal di\b\s+(.+)", "location"),
        ("routine", r"\bi usually\b\s+(.+)", "routine"),
        ("routine", r"\bbiasanya saya\b\s+(.+)", "routine"),
    )

    for _category, pattern, field in patterns:
        match = re.search(pattern, lower)
        if match:
            value = match.group(match.lastindex or 1)
            return structured_field or field, structured_value or _clean_text(value)

    if ":" in cleaned:
        key, value = cleaned.split(":", 1)
        key = _clean_text(key).casefold().replace(" ", "_")
        value = _clean_text(value)
        if key and value:
            return structured_field or key[:80], structured_value or value[:300]

    return structured_field, structured_value


def _infer_category(field: str | None) -> str:
    normalized = str(field or "").casefold()
    if normalized in {"name", "preferred_address", "disallowed_address"}:
        return "identity"
    if "preference" in normalized or "address" in normalized:
        return "preferences"
    if "location" in normalized or "timezone" in normalized:
        return "context"
    if "routine" in normalized:
        return "routines"
    if "goal" in normalized:
        return "goals"
    return "context"
