"""Apply Phase 4.15 patches to chat.py.

Adds two things:
  1. Import deterministic_profile helper
  2. Build & inject the profile runtime context block into volatile_context

Idempotent, bails on conflict.

Run:
    cd ~/my-assistant/backend
    python3 apply_phase415.py
"""

from __future__ import annotations

import sys
from pathlib import Path


CHAT_PATH = Path("app/routers/chat.py")


PATCHES: list[dict] = [
    # ---- Patch 1: import deterministic_profile renderer ----
    # Anchor on the user_mood_prompt import added in Zip 4. Safe because
    # that line is unique in the file and stable in position.
    {
        "name": "import render_profile_runtime_context",
        "anchor": "from app.services.user_mood_prompt import render_user_mood_block",
        "replacement": (
            "from app.services.user_mood_prompt import render_user_mood_block\n"
            "from app.services.deterministic_profile import render_profile_runtime_context"
        ),
        "already_present_marker": "from app.services.deterministic_profile import render_profile_runtime_context",
    },

    # ---- Patch 2: inject profile runtime block ----
    # Anchor on the user_mood_block injection from Zip 4. We add profile
    # context AFTER user_mood_block so it sits adjacent to user-state info.
    # Profile context is read from `context.identity` which was already
    # fetched earlier in the gather.
    {
        "name": "inject profile runtime block",
        "anchor": (
            "    # User mood (Layer A) — appended BEFORE companion mood so it sits\n"
            "    # higher in the context. User mood informs how the assistant should\n"
            "    # behave; companion mood is the assistant's own affect.\n"
            "    user_mood_block = render_user_mood_block(user_mood_ctx)\n"
            "    if user_mood_block:\n"
            "        volatile_context += \"\\n\\n\" + user_mood_block"
        ),
        "replacement": (
            "    # User mood (Layer A) — appended BEFORE companion mood so it sits\n"
            "    # higher in the context. User mood informs how the assistant should\n"
            "    # behave; companion mood is the assistant's own affect.\n"
            "    user_mood_block = render_user_mood_block(user_mood_ctx)\n"
            "    if user_mood_block:\n"
            "        volatile_context += \"\\n\\n\" + user_mood_block\n"
            "\n"
            "    # Deterministic profile context (Phase 4.15) — computes age from\n"
            "    # browser local date so the LLM doesn't have to. Reads identity\n"
            "    # already fetched via life_model.get_context.\n"
            "    profile_runtime_block = render_profile_runtime_context(\n"
            "        context.get(\"identity\") if isinstance(context, dict) else None,\n"
            "        body.ui_context,\n"
            "    )\n"
            "    if profile_runtime_block:\n"
            "        volatile_context += \"\\n\\n\" + profile_runtime_block"
        ),
        "already_present_marker": "profile_runtime_block = render_profile_runtime_context",
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
            print(f"       Looking for:\n       {patch['anchor'][:160]}...")
            print("       chat.py may have been modified — refusing to patch.")
            return 2
        src = src.replace(patch["anchor"], patch["replacement"], 1)
        applied.append(patch["name"])

    if src == original:
        print("All patches already applied. No changes made.")
        return 0

    import ast
    try:
        ast.parse(src)
    except SyntaxError as exc:
        print(f"ERROR: patched file has syntax error: {exc}")
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
