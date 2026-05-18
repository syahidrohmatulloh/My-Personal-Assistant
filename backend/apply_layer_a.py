"""Apply Zip 4 Layer A patches to chat.py.

Usage:
    cd ~/my-assistant/backend
    python apply_layer_a.py

Idempotent: re-running is a no-op (each patch checks "already applied").
Bails on conflict: if chat.py doesn't match expected anchors, no changes made
and you get an error pointing to which patch failed. Manual fix possible
from the patch source below.
"""

from __future__ import annotations

import sys
from pathlib import Path


CHAT_PATH = Path("app/routers/chat.py")


PATCHES: list[dict] = [
    # ---- Patch 1: import user_mood services ----
    {
        "name": "import user_mood services",
        "anchor": "from app.services import (\n    attachments,\n    companion,\n    companion_mode,\n    conversation_summary,\n    life_model,\n    memory,\n)",
        "replacement": (
            "from app.services import (\n"
            "    attachments,\n"
            "    companion,\n"
            "    companion_mode,\n"
            "    conversation_summary,\n"
            "    life_model,\n"
            "    memory,\n"
            "    user_mood,\n"
            ")\n"
            "from app.services.user_mood_prompt import render_user_mood_block"
        ),
        "already_present_marker": "user_mood_prompt import render_user_mood_block",
    },

    # ---- Patch 2: add user_mood to asyncio.gather ----
    # We add the call as the LAST positional in gather + extend the tuple unpack.
    # We do this with a clearly anchored "companion.get_current_mood(user_id)," line.
    {
        "name": "add user_mood.infer_user_mood to asyncio.gather",
        "anchor": "        # Current companion mood. Returns None if mood is not applicable\n        # per user settings (mode != 'partner' or realism != 'dynamic').\n        companion.get_current_mood(user_id),\n    )",
        "replacement": (
            "        # Current companion mood. Returns None if mood is not applicable\n"
            "        # per user settings (mode != 'partner' or realism != 'dynamic').\n"
            "        companion.get_current_mood(user_id),\n"
            "        # User mood (Layer A) — inferred from emotional_state + current msg.\n"
            "        # Read-only, never overwrites companion mood. Returns has_data: False\n"
            "        # when there's nothing useful to render.\n"
            "        user_mood.infer_user_mood(user_id, current_message=body.message),\n"
            "    )"
        ),
        "already_present_marker": "user_mood.infer_user_mood(user_id",
    },

    # ---- Patch 3: extend tuple unpacking with user_mood_ctx ----
    {
        "name": "extend tuple unpacking",
        "anchor": (
            "    (\n"
            "        convo_result,\n"
            "        user_message_id,\n"
            "        context,\n"
            "        legacy_memories,\n"
            "        related_summaries,\n"
            "        attachment_rows,\n"
            "        detected_mode,\n"
            "        companion_settings_row,\n"
            "        current_mood,\n"
            "    ) = await asyncio.gather("
        ),
        "replacement": (
            "    (\n"
            "        convo_result,\n"
            "        user_message_id,\n"
            "        context,\n"
            "        legacy_memories,\n"
            "        related_summaries,\n"
            "        attachment_rows,\n"
            "        detected_mode,\n"
            "        companion_settings_row,\n"
            "        current_mood,\n"
            "        user_mood_ctx,\n"
            "    ) = await asyncio.gather("
        ),
        "already_present_marker": "        user_mood_ctx,\n    ) = await asyncio.gather(",
    },

    # ---- Patch 4: inject user_mood block into volatile_context ----
    # Anchored right after the companion-mood-block injection so user mood
    # appears separately and clearly labeled.
    {
        "name": "inject user_mood block",
        "anchor": (
            "    # Companion mood block — ONLY injected if user has dynamic mood enabled."
        ),
        "replacement": (
            "    # User mood (Layer A) — appended BEFORE companion mood so it sits\n"
            "    # higher in the context. User mood informs how the assistant should\n"
            "    # behave; companion mood is the assistant's own affect.\n"
            "    user_mood_block = render_user_mood_block(user_mood_ctx)\n"
            "    if user_mood_block:\n"
            "        volatile_context += \"\\n\\n\" + user_mood_block\n"
            "\n"
            "    # Companion mood block — ONLY injected if user has dynamic mood enabled."
        ),
        "already_present_marker": "user_mood_block = render_user_mood_block",
    },
]


def main() -> int:
    if not CHAT_PATH.exists():
        print(f"ERROR: {CHAT_PATH} not found. Run from backend/ directory.")
        return 1

    src = CHAT_PATH.read_text()
    original = src
    applied: list[str] = []
    skipped: list[str] = []

    for patch in PATCHES:
        if patch["already_present_marker"] in src:
            skipped.append(patch["name"])
            continue
        if patch["anchor"] not in src:
            print(f"ERROR: anchor not found for patch: {patch['name']}")
            print("       chat.py may have been modified — refusing to patch blindly.")
            print(f"       Looking for:\n       {patch['anchor'][:120]}...")
            return 2
        src = src.replace(patch["anchor"], patch["replacement"], 1)
        applied.append(patch["name"])

    if src == original:
        print("All patches already applied. No changes made.")
        return 0

    # Quick syntax check before writing
    import ast
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"ERROR: patched file has syntax error: {exc}")
        print("       No changes written.")
        return 3

    CHAT_PATH.write_text(src)
    print(f"Patched {CHAT_PATH}:")
    for name in applied:
        print(f"  + {name}")
    for name in skipped:
        print(f"  · skipped (already applied): {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
