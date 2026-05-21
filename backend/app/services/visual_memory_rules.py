"""Visual memory rules.

Purpose:
- Uploaded images should not all become durable memories.
- Screenshot/debug/UI images are useful for the current conversation but should
  usually not pollute long-term memory.
- Personal/meaningful images can become structured memory candidates.

This module is intentionally generic:
- no user-specific hardcoding
- no assistant-name hardcoding
- no private location hardcoding
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class VisualMemoryDecision:
    should_store: bool
    content: str
    kind: str
    category: str
    structured_field: str
    structured_value: str
    confidence: float
    reason: str


SKIP_PATTERNS = (
    r"\bscreenshot\b",
    r"\bterminal\b",
    r"\bcode\b",
    r"\bdeveloper tools?\b",
    r"\bdebug\b",
    r"\berror message\b",
    r"\bwebpage\b",
    r"\bwebsite\b",
    r"\bapp interface\b",
    r"\buser interface\b",
    r"\bui\b",
    r"\bbrowser\b",
    r"\bchatgpt\b",
    r"\bvercel\b",
    r"\bsupabase\b",
    r"\bfly\.io\b",
    r"\bdashboard\b",
    r"\bsettings page\b",
    r"\bmemory review\b",
)

PERSONAL_PHOTO_PATTERNS = (
    r"\bperson\b",
    r"\bpeople\b",
    r"\bman\b",
    r"\bwoman\b",
    r"\bchild\b",
    r"\bfamily\b",
    r"\bsmil(?:e|ing)\b",
    r"\bselfie\b",
    r"\bportrait\b",
)

TRAVEL_OR_PLACE_PATTERNS = (
    r"\btravel\b",
    r"\btrip\b",
    r"\bvacation\b",
    r"\bairport\b",
    r"\bhotel\b",
    r"\brestaurant\b",
    r"\bharbor\b",
    r"\bstatue\b",
    r"\bbeach\b",
    r"\bcity\b",
    r"\blandmark\b",
    r"\bview\b",
)

FOOD_PATTERNS = (
    r"\bfood\b",
    r"\bmeal\b",
    r"\bdinner\b",
    r"\blunch\b",
    r"\bbreakfast\b",
    r"\bdrink\b",
    r"\btea\b",
    r"\bcoffee\b",
    r"\bnoodle\b",
    r"\brice\b",
    r"\bfried\b",
    r"\btakeout\b",
    r"\bbox contains\b",
)


def decide_visual_memory(description: str | None) -> VisualMemoryDecision | None:
    text = _clean(description)
    lower = text.casefold()

    if not text:
        return None

    if _matches_any(lower, SKIP_PATTERNS):
        return VisualMemoryDecision(
            should_store=False,
            content="",
            kind="context",
            category="life_context",
            structured_field="visual_memory_skipped",
            structured_value="screenshot_or_debug_image",
            confidence=0.85,
            reason="skip_screenshot_or_debug",
        )

    if _matches_any(lower, PERSONAL_PHOTO_PATTERNS) and _matches_any(lower, TRAVEL_OR_PLACE_PATTERNS):
        value = _compact_visual_value(text)
        return VisualMemoryDecision(
            should_store=True,
            content=f"User shared a meaningful personal/travel photo: {value}",
            kind="context",
            category="life_context",
            structured_field="visual_memory_personal_travel_photo",
            structured_value=value,
            confidence=0.74,
            reason="personal_travel_photo",
        )

    if _matches_any(lower, PERSONAL_PHOTO_PATTERNS):
        value = _compact_visual_value(text)
        return VisualMemoryDecision(
            should_store=True,
            content=f"User shared a meaningful personal photo: {value}",
            kind="context",
            category="life_context",
            structured_field="visual_memory_personal_photo",
            structured_value=value,
            confidence=0.70,
            reason="personal_photo",
        )

    if _matches_any(lower, FOOD_PATTERNS):
        value = _compact_visual_value(text)
        return VisualMemoryDecision(
            should_store=True,
            content=f"User shared a food or drink photo: {value}",
            kind="preference",
            category="preferences",
            structured_field="visual_memory_food_photo",
            structured_value=value,
            confidence=0.66,
            reason="food_photo",
        )

    if _matches_any(lower, TRAVEL_OR_PLACE_PATTERNS):
        value = _compact_visual_value(text)
        return VisualMemoryDecision(
            should_store=True,
            content=f"User shared a meaningful place/travel photo: {value}",
            kind="context",
            category="life_context",
            structured_field="visual_memory_place_photo",
            structured_value=value,
            confidence=0.68,
            reason="place_photo",
        )

    return VisualMemoryDecision(
        should_store=False,
        content="",
        kind="context",
        category="life_context",
        structured_field="visual_memory_skipped",
        structured_value="generic_image",
        confidence=0.60,
        reason="skip_generic_image",
    )


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def _compact_visual_value(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"^user shared an image:\s*", "", text, flags=re.IGNORECASE)
    return text[:300].strip(" ,.;:-")
