"""User mood context rendering for the system prompt.

This renderer is intentionally separate from companion mood.

User mood = the user's inferred emotional condition.
Companion mood = Aliyya's own relational/affective mood.

This block is only for tone/support strategy. It must not drive UI ambience,
must not overwrite memory, and must not affect companion_mood_state.
"""

from __future__ import annotations

from typing import Any

from app.services.user_mood import UserMoodContext


MAX_CAUSES = 4
MAX_EVIDENCE = 3
MAX_EVIDENCE_CHARS = 120


def render_user_mood_block(ctx: UserMoodContext | None) -> str | None:
    """Render compact user-mood context, or None if signal is absent."""
    if not ctx or not ctx.get("has_data"):
        return None

    latest = ctx.get("latest") or {}
    baseline = ctx.get("baseline") or {}
    delta = ctx.get("delta") or {}
    causal = _compact_list(ctx.get("causal") or [], limit=MAX_CAUSES)
    evidence = _compact_list(ctx.get("evidence") or [], limit=MAX_EVIDENCE)
    confidence = _safe_float(ctx.get("confidence"), default=0.0)
    sample_size = int(ctx.get("sample_size") or 0)
    current_signal = ctx.get("current_message_signal")

    lines: list[str] = [
        "## USER MOOD CONTEXT",
        "- User mood: inferred emotional context for tone/support strategy only.",
        "- Purpose: adapt tone/support strategy only. This is the USER's inferred state, not Aliyya's companion mood.",
        "- This is the USER's emotional state, inferred from their own notes — separate from your own companion mood.",
        "- Never recite this state back to the user as a label. Respond TO the state through tone, not BY naming it.",
    ]

    latest_bits = _format_axis_snapshot(latest, precision=0)
    if latest_bits:
        lines.append(f"- Latest self-report: {latest_bits}")

    if baseline and sample_size >= 3:
        baseline_bits = _format_axis_snapshot(baseline, precision=1)
        if baseline_bits:
            lines.append(f"- 30-day baseline ({sample_size} self-reports): {baseline_bits}")

        delta_bits = _format_delta(delta)
        if delta_bits:
            lines.append(f"- Baseline delta: {delta_bits}")

    if causal:
        lines.append("- Recent possible causes/tags: " + "; ".join(causal))

    if evidence:
        lines.append("- Supporting signals, summarized/trimmed:")
        for item in evidence:
            lines.append(f"  · {_truncate(str(item), MAX_EVIDENCE_CHARS)}")

    if current_signal and current_signal.get("mood_hint"):
        hint = str(current_signal.get("mood_hint") or "").strip()
        matched = _compact_list(current_signal.get("matched_keywords") or [], limit=5)
        if hint:
            suffix = f" keywords={matched}" if matched else ""
            lines.append(
                f"- Current message hint: {hint}{suffix}. Keyword-only; current user correction wins."
            )

    lines.append(f"- Confidence: {confidence:.2f}")
    lines.extend(
        [
            "- Suggested use: adjust pacing, warmth, brevity, and support-vs-solution balance.",
            "- Avoid: naming the user's mood as a fact, over-therapizing, dismissive jokes, or changing companion mood.",
            "- If the user contradicts this inference, follow the user's current message.",
        ]
    )

    return "\n".join(lines)


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_list(items: list[Any], *, limit: int) -> list[str]:
    out: list[str] = []
    for item in items[:limit]:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_axis_snapshot(snap: dict[str, Any], *, precision: int = 0) -> str:
    parts: list[str] = []
    for axis in ("mood", "energy", "stress"):
        value = snap.get(axis)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        if precision:
            parts.append(f"{axis} {numeric:+.{precision}f}")
        else:
            parts.append(f"{axis} {int(round(numeric)):+d}")

    return ", ".join(parts)


def _format_delta(delta: dict[str, Any]) -> str:
    parts: list[str] = []
    for axis in ("mood", "energy", "stress"):
        label = delta.get(f"label_{axis}")
        if label in (None, "unknown", "near baseline"):
            continue

        value = delta.get(axis)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue

        parts.append(f"{axis} {label} ({numeric:+.1f})")

    return ", ".join(parts) if parts else "near baseline"
