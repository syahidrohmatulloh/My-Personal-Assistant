"""Apply Zip 7 polish patch to frontend/app/memories/page.tsx.

Removes the redundant `{memory.kind}` Badge — it duplicates information already
shown by the category Badge above it. (`kind` is legacy enum: fact/preference/
context/plan. `category` is the new orthogonal enum. They mean almost the same.)

Idempotent. Bails on conflict.

Usage:
    cd ~/my-assistant
    python3 frontend/apply_memories_polish.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PATH = Path("frontend/app/memories/page.tsx")


# We grep'd the file: the pill rendering is around line 1251-1254:
#   <Badge>{memory.category || "other"}</Badge>
#   <Badge>{memory.kind}</Badge>                    <-- this redundant
#   <Badge>conf {confidence}</Badge>
#
# Anchor on the category + kind sequence (uniquely identifiable in the file).

ANCHOR = (
    '          <Badge>{memory.category || "other"}</Badge>\n'
    '          <Badge>{memory.kind}</Badge>\n'
    '          <Badge>conf {confidence}</Badge>'
)

REPLACEMENT = (
    '          <Badge>{memory.category || "other"}</Badge>\n'
    '          <Badge>conf {confidence}</Badge>'
)

ALREADY_DONE_MARKER = (
    '          <Badge>{memory.category || "other"}</Badge>\n'
    '          <Badge>conf {confidence}</Badge>'
)


def main() -> int:
    if not PATH.exists():
        print(f"ERROR: {PATH} not found. Run from project root.")
        return 1

    src = PATH.read_text()

    # Idempotency: if the kind Badge is gone, do nothing.
    if "<Badge>{memory.kind}</Badge>" not in src:
        print("memory.kind Badge already removed. No changes.")
        return 0

    if ANCHOR not in src:
        # Fall back: search with looser whitespace match
        import re
        loose = re.compile(
            r'<Badge>\{memory\.category[^}]+\}</Badge>\s*'
            r'<Badge>\{memory\.kind\}</Badge>\s*'
            r'<Badge>conf \{confidence\}</Badge>',
            re.MULTILINE,
        )
        m = loose.search(src)
        if not m:
            print("ERROR: anchor not found. Manual fix needed.")
            print("       Look for `<Badge>{memory.kind}</Badge>` and delete that line.")
            print(f"       Expected near line ~1252 of {PATH}.")
            return 2
        # Loose match found — use regex sub
        new_src = loose.sub(
            '<Badge>{memory.category || "other"}</Badge>\n'
            '          <Badge>conf {confidence}</Badge>',
            src,
            count=1,
        )
    else:
        new_src = src.replace(ANCHOR, REPLACEMENT, 1)

    PATH.write_text(new_src)
    print(f"Patched {PATH}: removed redundant `kind` Badge from memory pills.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
