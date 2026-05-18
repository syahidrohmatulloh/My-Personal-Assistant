#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.prompt_builder import render_client_time_context

block = render_client_time_context(
    {
        "timezone": "Asia/Jakarta",
        "local_time": "2026-05-18 13:05:00",
        "utc_offset_minutes": 420,
        "locale": "id-ID",
        "source": "browser",
        "captured_at_utc": "2026-05-18T06:05:00.000Z",
    },
    {},
)

print(block)
assert "Asia/Jakarta" in block
assert "13:05" in block
assert "GMT+7" in block
assert "source of truth" in block
print("OK: client local time context rendered correctly")
