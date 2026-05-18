"""Apply Phase 4.15 memories list filter patch.

Targets `app/routers/memories.py` — adds `.eq("superseded", False)` to the
list endpoint so superseded memories don't appear in the UI.

Idempotent. Bails on conflict.

This patcher tries 3 common patterns to find the list query. If none match,
prints a clear error and exits 2 — you can patch manually using the snippet
at the end of the error output.

Run:
    cd ~/my-assistant/backend
    python3 apply_memories_filter.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


PATH = Path("app/routers/memories.py")

# Anchors we'll try, in order of specificity. Each is the EXPECTED current
# query chain. Replacement just inserts the superseded filter before .order(...).
ANCHOR_PATTERNS = [
    # Pattern A: explicit user_id eq + order by created_at
    (
        '.table("memories")',
        re.compile(
            r'(\.table\("memories"\)\s*'
            r'\.select\([^)]+\)\s*'
            r'\.eq\("user_id", user_id\)\s*)'
            r'(\.order\()',
            re.MULTILINE,
        ),
    ),
    # Pattern B: just looks for .order after a memories select on user_id
    (
        '.eq("user_id"',
        re.compile(
            r'(\.eq\("user_id",\s*user_id\)\s*'
            r')(\.order\()',
            re.MULTILINE,
        ),
    ),
]


SUPERSEDED_FILTER = '.eq("superseded", False)\n        '


def main() -> int:
    if not PATH.exists():
        print(f"ERROR: {PATH} not found. Run from backend/ directory.")
        return 1

    src = PATH.read_text()

    if '.eq("superseded", False)' in src:
        print("Filter already present in memories.py. No changes made.")
        return 0

    for marker, pattern in ANCHOR_PATTERNS:
        if marker not in src:
            continue
        new_src, count = pattern.subn(
            lambda m: m.group(1).rstrip() + "\n        " + SUPERSEDED_FILTER + m.group(2),
            src,
            count=1,
        )
        if count == 0:
            continue
        # Validate Python.
        import ast
        try:
            ast.parse(new_src)
        except SyntaxError as exc:
            print(f"ERROR: patched memories.py has syntax error: {exc}")
            print("       No changes written. Manual patch needed.")
            return 3
        PATH.write_text(new_src)
        print(f"Patched {PATH} (matched pattern with marker {marker!r}).")
        return 0

    # No pattern matched. Show user how to manually patch.
    print("ERROR: could not find a recognizable list query in memories.py.")
    print()
    print("Manual patch needed. Find the list endpoint (it has .table('memories'))")
    print("and add this line before .order(...):")
    print()
    print('        .eq("superseded", False)')
    print()
    print("If your query uses `superseded = false` rather than `superseded is null`,")
    print("the filter is correct. If the column is missing, run Zip 5 SQL first.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
