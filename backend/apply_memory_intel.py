"""Apply Zip 5 (memory intelligence) patches to chat.py.

Adds one background task: memory_intelligence.extract_and_persist runs in
parallel with the existing memory.extract_and_save after the chat reply.

Usage:
    cd ~/my-assistant/backend
    python3 apply_memory_intel.py

Idempotent + bails on conflict.
"""

from __future__ import annotations

import sys
from pathlib import Path


CHAT_PATH = Path("app/routers/chat.py")


PATCHES: list[dict] = [
    # ---- Patch 1: import memory_intelligence ----
    # Anchor on the existing memory import line, add a sibling import below it.
    {
        "name": "import memory_intelligence",
        "anchor": "from app.services import (\n    attachments,\n    companion,\n    companion_mode,\n    conversation_summary,\n    life_model,\n    memory,\n    user_mood,\n)",
        "replacement": (
            "from app.services import (\n"
            "    attachments,\n"
            "    companion,\n"
            "    companion_mode,\n"
            "    conversation_summary,\n"
            "    life_model,\n"
            "    memory,\n"
            "    memory_intelligence,\n"
            "    user_mood,\n"
            ")"
        ),
        "already_present_marker": "    memory_intelligence,\n    user_mood,",
    },

    # ---- Patch 2: schedule memory_intelligence as background task ----
    # Anchor on the existing memory.extract_and_save background task call.
    # We schedule the new task right next to it so both run in parallel after reply.
    {
        "name": "schedule memory_intelligence extraction",
        "anchor": (
            "    # Background memory extraction (writes to legacy unstructured table)\n"
            "    background_tasks.add_task(\n"
            "        memory.extract_and_save,\n"
            "        user_id=user_id,\n"
            "        conversation_id=conversation_id,\n"
            "        recent_messages=[\n"
            "            {\"role\": \"user\", \"content\": user_message},\n"
            "            {\"role\": \"assistant\", \"content\": assistant_text},\n"
            "        ],\n"
            "    )"
        ),
        "replacement": (
            "    # Background memory extraction (writes to legacy unstructured table)\n"
            "    background_tasks.add_task(\n"
            "        memory.extract_and_save,\n"
            "        user_id=user_id,\n"
            "        conversation_id=conversation_id,\n"
            "        recent_messages=[\n"
            "            {\"role\": \"user\", \"content\": user_message},\n"
            "            {\"role\": \"assistant\", \"content\": assistant_text},\n"
            "        ],\n"
            "    )\n"
            "\n"
            "    # Background memory intelligence — wider window, structured identity\n"
            "    # writes, conflict resolution via supersede chain. Reads `messages`\n"
            "    # (already in scope from the streamer) plus the new assistant reply.\n"
            "    background_tasks.add_task(\n"
            "        memory_intelligence.extract_and_persist,\n"
            "        user_id=user_id,\n"
            "        conversation_id=conversation_id,\n"
            "        recent_messages=[\n"
            "            *messages,\n"
            "            {\"role\": \"assistant\", \"content\": assistant_text},\n"
            "        ],\n"
            "    )"
        ),
        "already_present_marker": "memory_intelligence.extract_and_persist,",
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

    # Syntax check before writing.
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
