"""User mood context rendering for the system prompt.

Separate from prompt_builder.py so the existing flow is untouched. The chat
router calls `render_user_mood_block(ctx)` after building the rest of the
volatile context and appends the result if non-empty.

Output is a single markdown block — clearly labeled "User mood (inferred)"
so Claude knows this is the USER's state, not its own.
"""

from __future__ import annotations

from typing import Any

from app.services.user_mood import UserMoodContext


def render_user_mood_block(ctx: UserMoodContext | None) -> str | None:
    """Render the user-mood context block, or None if not enough signal.

    Block intentionally separate from the companion mood block. Use this
    output to inform tone and support strategy — not to drive ambient UI
    or to overwrite the assistant's own (companion) mood.
    """
    if not ctx or not ctx.get("has_data"):
        return None

    lines: list[str] = ["## User mood (inferred — for tone/support strategy only)"]

    latest = ctx.get("latest") or {}
    baseline = ctx.get("baseline") or {}
    delta = ctx.get("delta") or {}
    causal = ctx.get("causal") or []
    evidence = ctx.get("evidence") or []
    confidence = ctx.get("confidence", 0.0)
    sample_size = ctx.get("sample_size", 0)
    current_signal = ctx.get("current_message_signal")

    # 1. Latest snapshot (only show populated axes)
    latest_bits = _format_axis_snapshot(latest, label="latest")
    if latest_bits:
        lines.append(f"- Latest self-report: {latest_bits}")

    # 2. Baseline + delta (only if we have enough baseline data)
    if baseline and sample_size >= 3:
        baseline_bits = _format_axis_snapshot(baseline, label="baseline", precision=1)
        if baseline_bits:
            lines.append(
                f"- 30-day baseline (from {sample_size} self-reports): {baseline_bits}"
            )

        delta_bits = _format_delta(delta)
        if delta_bits:
            lines.append(f"- Versus baseline: {delta_bits}")

    # 3. Causal context — extracted phrases / tags
    if causal:
        lines.append(
            "- Recent attributed causes: " + "; ".join(f"\"{c}\"" for c in causal)
        )

    # 4. Evidence — dated quotes from notes
    if evidence:
        lines.append("- Evidence (verbatim from journal):")
        for e in evidence:
            lines.append(f"  · {e}")

    # 5. Current-message signal — surface as low-confidence hint only
    if current_signal and current_signal.get("mood_hint"):
        hint = current_signal["mood_hint"]
        matched = current_signal.get("matched_keywords", [])
        kw_str = ", ".join(f"'{k}'" for k in matched) if matched else ""
        lines.append(
            f"- Current message tone hint: \"{hint}\""
            + (f" (keywords: {kw_str})" if kw_str else "")
            + " — keyword-only signal, treat as hypothesis."
        )

    # 6. Confidence header
    lines.append(f"- Confidence: {confidence:.2f}")

    # 7. Hard usage rules — keep separate from companion mood
    lines.extend([
        "",
        "**Rules for using this:**",
        "- This is the USER's emotional state, inferred from their own notes — separate from your own companion mood.",
        "- Use it to calibrate tone, pacing, and whether to lead with support vs solutions. NOT to drive UI ambience or your own affect.",
        "- Higher-confidence signals (>0.6) can shape tone meaningfully. Below that, treat as a soft hint.",
        "- Never recite this state back to the user as a label (\"I see you're stressed\"). Respond TO the state through tone, not BY naming it.",
        "- If the user contradicts this inference in conversation, the user's current message wins.",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_axis_snapshot(
    snap: dict[str, Any], *, label: str, precision: int = 0
) -> str:
    """Format mood/energy/stress as a compact one-liner. Skip None axes."""
    fmt = f"{{:+.{precision}f}}" if precision else "{:+d}"
    parts: list[str] = []
    for axis in ("mood", "energy", "stress"):
        v = snap.get(axis)
        if v is None:
            continue
        if precision:
            parts.append(f"{axis} {fmt.format(v)}")
        else:
            parts.append(f"{axis} {fmt.format(int(round(v)))}")
    return ", ".join(parts)


def _format_delta(delta: dict[str, Any]) -> str:
    """Format the delta block — only mention axes that meaningfully shifted."""
    parts: list[str] = []
    for axis in ("mood", "energy", "stress"):
        label = delta.get(f"label_{axis}")
        if label in (None, "unknown", "near baseline"):
            continue
        d = delta.get(axis)
        if d is None:
            continue
        parts.append(f"{axis} {label} ({d:+.1f})")
    if not parts:
        return "all axes near baseline"
    return ", ".join(parts)
