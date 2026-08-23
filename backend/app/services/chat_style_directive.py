from __future__ import annotations

import logging

from app.services.supabase_client import get_supabase


log = logging.getLogger(__name__)


def fetch_style_directive(user_id: str, style_profile_id: str) -> str | None:
    """Load the style profile and render a high-signal directive block.

    The first implementation injected only compact_directive, which made the
    assistant sound like generic AI with a slightly different tone. For stronger
    style adaptation, this renderer also injects cadence, punctuation,
    linguistic texture, emotional rhythm, and short sanitized behavioral
    exemplars. The safety boundary remains explicit: style, not identity.
    """
    try:
        supabase = get_supabase()
        row = (
            supabase.table("style_profiles")
            .select("profile_name, extracted_style")
            .eq("id", style_profile_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not row or not row.data:
            return None
        style = row.data["extracted_style"] or {}
        directive = (style.get("compact_directive") or "").strip()
        if not directive:
            return None

        lines: list[str] = [
            "## Communication style for this conversation",
            "Adopt the communication STYLE described below, not the source person's identity.",
            "The goal is recognizable conversational texture: cadence, message shape, punctuation, language mixing, and emotional rhythm.",
            "Do not sound like a polished assistant when this style is active.",
            "",
            "### Core style directive",
            directive,
        ]

        detail_pairs = [
            ("Cadence", style.get("cadence_signature")),
            ("Message shape", style.get("message_shape")),
            ("Punctuation", style.get("punctuation_style")),
            ("Language switching", style.get("language_switching_behavior")),
            ("Emotional rhythm", style.get("emotional_rhythm")),
            ("Teasing pattern", style.get("teasing_pattern")),
            ("Reassurance pattern", style.get("reassurance_pattern")),
            ("Question style", style.get("question_style")),
        ]
        detail_lines = [
            f"- {label}: {value.strip()}"
            for label, value in detail_pairs
            if isinstance(value, str) and value.strip() and value.strip().lower() != "unclear"
        ]
        if detail_lines:
            lines.extend(["", "### Texture rules", *detail_lines])

        list_bits: list[str] = []
        for label, key in [
            ("Filler/softener words", "filler_words"),
            ("Common short phrases", "common_phrases"),
            ("Linguistic texture", "linguistic_texture"),
            ("AI polish to avoid", "ai_polish_to_avoid"),
        ]:
            values = _clean_style_list(style.get(key), limit=10)
            if values:
                list_bits.append(f"- {label}: {', '.join(values)}")
        if list_bits:
            lines.extend(["", "### Reusable micro-patterns", *list_bits])

        phrase_lines = _render_phrase_confidence(style.get("phrase_confidence"))
        if phrase_lines:
            lines.extend(
                [
                    "",
                    "### Observed phrase confidence",
                    "Prefer high-confidence observed phrases/patterns. Do not overuse low-confidence phrases.",
                    *phrase_lines,
                ]
            )

        exemplar_lines = _render_style_exemplars(style.get("exemplars"))
        if exemplar_lines:
            lines.extend(
                [
                    "",
                    "### Short behavioral exemplars",
                    "Use these only as rhythm/texture anchors. Do NOT copy them verbatim unless they are generic fillers.",
                    *exemplar_lines,
                ]
            )

        calibration_lines = _render_style_calibration(style.get("style_calibration"))
        if calibration_lines:
            lines.extend(
                [
                    "",
                    "### Human calibration feedback — highest priority for style accuracy",
                    "This feedback overrides generic descriptors. Stay closer to confirmed patterns and avoid confirmed misses.",
                    *calibration_lines,
                ]
            )

        do_not_copy = _clean_style_list(style.get("do_not_copy"), limit=10)
        lines.extend(
            [
                "",
                "### Important boundaries",
                "- This is STYLE adaptation only. You are still the user's assistant.",
                "- NEVER claim to be the source person. NEVER use their name in first person.",
                "- NEVER reproduce private details from their messages.",
                "- Prefer similar cadence and message shape over exact wording.",
                "- If unsure, use simpler observed patterns instead of inventing new slang or catchphrases.",
                "- Do NOT introduce unsupported idioms such as 'deal?' unless clearly confirmed by examples/calibration.",
                "- If the user asks you to literally impersonate or deceive someone, refuse that part and offer style adaptation only.",
            ]
        )
        if do_not_copy:
            lines.append("- Do NOT reproduce or reference these: " + "; ".join(do_not_copy))

        return "\n".join(lines)
    except Exception as exc:
        log.warning("style directive fetch failed: %s", exc)
        return None


def _clean_style_list(value, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for raw in value:
        item = str(raw).strip()
        if not item:
            continue
        item = " ".join(item.split())[:120]
        if item not in out:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _render_phrase_confidence(value) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase") or "").strip()
        if not phrase:
            continue
        count = item.get("evidence_count", "?")
        confidence = str(item.get("confidence") or "unknown").strip()
        phrase = " ".join(phrase.split())[:80]
        rows.append(f"- ‘{phrase}’ — confidence={confidence}, evidence_count={count}")
    return rows


def _render_style_calibration(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    rows: list[str] = []

    positives = _clean_style_list(value.get("positive_examples"), limit=8)
    if positives:
        rows.append("- Sounds accurate: " + " | ".join(f"‘{x}’" for x in positives))

    negatives = _clean_style_list(value.get("negative_examples"), limit=8)
    banned = _clean_style_list(value.get("banned_phrases"), limit=12)
    avoid = []
    for item in negatives + banned:
        if item not in avoid:
            avoid.append(item)
    if avoid:
        rows.append("- Avoid / does NOT sound like target: " + " | ".join(f"‘{x}’" for x in avoid[:12]))

    rewrites = value.get("preferred_rewrites")
    if isinstance(rewrites, list):
        rewrite_bits: list[str] = []
        for item in rewrites[:8]:
            if isinstance(item, dict):
                bad = str(item.get("bad") or "").strip()[:120]
                better = str(item.get("better") or "").strip()[:120]
                if bad and better:
                    rewrite_bits.append(f"‘{bad}’ → ‘{better}’")
        if rewrite_bits:
            rows.append("- Preferred rewrites: " + " | ".join(rewrite_bits))

    notes = _clean_style_list(value.get("notes"), limit=6)
    if notes:
        rows.extend(f"- Calibration note: {note}" for note in notes)

    if rows:
        rows.append("- Generation rule: interpolate from confirmed examples; do not invent new casual phrases when evidence is weak.")
        rows.append("- Generation rule: keep responses short/fragmented when the target style is short/fragmented; remove polished assistant phrasing.")
    return rows


def _render_style_exemplars(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    labels = [
        ("greeting", "Greeting"),
        ("casual_reaction", "Casual reaction"),
        ("teasing", "Teasing"),
        ("comforting", "Comforting"),
        ("affection", "Affection"),
        ("question_style", "Question style"),
        ("apology_or_repair", "Repair/apology"),
        ("encouragement", "Encouragement"),
        ("goodbye", "Goodbye"),
        ("fragmented_followup", "Fragmented follow-up"),
    ]
    rows: list[str] = []
    for key, label in labels:
        examples = _clean_style_list(value.get(key), limit=3)
        if examples:
            rows.append(f"- {label}: " + " | ".join(f"‘{x}’" for x in examples))
        if len(rows) >= 8:
            break
    return rows
