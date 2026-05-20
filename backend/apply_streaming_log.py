"""Apply Zip 7 patch to backend/app/routers/chat.py.

Improves the streaming error path:
  - Before: `except Exception as exc: yield {..., 'message': str(exc)}`
            No logging, raw exception message exposed to client.
  - After:  Full stack trace logged via log.exception(), generic message sent.

Idempotent. Bails on conflict.

Usage:
    cd ~/my-assistant/backend
    python3 apply_streaming_log.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PATH = Path("app/routers/chat.py")


# From your grep output, around line 996-997 in chat.py:
#     except Exception as exc:  # noqa: BLE001
#         yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
#         return
#
# We want to add log.exception() and use a generic client message.

ANCHOR = (
    "    except Exception as exc:  # noqa: BLE001\n"
    "        yield f\"data: {json.dumps({'type': 'error', 'message': str(exc)})}\\n\\n\"\n"
    "        return"
)

REPLACEMENT = (
    "    except Exception as exc:  # noqa: BLE001\n"
    "        log.exception(\"chat: streaming failed (user=%s)\", user_id[:8])\n"
    "        yield (\n"
    "            \"data: \"\n"
    "            + json.dumps({\"type\": \"error\", \"message\": \"Internal error during streaming\"})\n"
    "            + \"\\n\\n\"\n"
    "        )\n"
    "        return"
)

ALREADY_PRESENT = "log.exception(\"chat: streaming failed"


def main() -> int:
    if not PATH.exists():
        print(f"ERROR: {PATH} not found. Run from backend/ directory.")
        return 1

    src = PATH.read_text()

    if ALREADY_PRESENT in src:
        print("Streaming log already added. No changes.")
        return 0

    if ANCHOR not in src:
        print("ERROR: anchor not found. The streaming except block may have been modified.")
        print("       Looking for:")
        for line in ANCHOR.splitlines():
            print(f"         {line}")
        print()
        print("       Find the streaming error block (around line 996) and manually replace")
        print("       `str(exc)` with a generic message, plus add log.exception() above it.")
        return 2

    new_src = src.replace(ANCHOR, REPLACEMENT, 1)

    # Syntax check
    import ast
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"ERROR: patched file has syntax error: {e}")
        return 3

    PATH.write_text(new_src)
    print(f"Patched {PATH}: streaming error now logs full trace, sends generic message.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
