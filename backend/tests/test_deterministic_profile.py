"""Tests for deterministic_profile service.

Pure Python — no DB / network. Run:
    cd backend && uv run python tests/test_deterministic_profile.py
or:
    cd backend && uv run pytest tests/test_deterministic_profile.py -v
"""

from __future__ import annotations

import inspect
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.deterministic_profile import (
    calculate_age,
    format_birthday,
    parse_birthdate,
    parse_client_local_date,
    render_profile_runtime_context,
)


# ---------------------------------------------------------------------------
# parse_birthdate
# ---------------------------------------------------------------------------


def test_parse_iso_date():
    assert parse_birthdate("1995-01-07") == date(1995, 1, 7)


def test_parse_id_format_with_year():
    assert parse_birthdate("7 Januari 1995") == date(1995, 1, 7)


def test_parse_en_format_with_year():
    assert parse_birthdate("January 7, 1995") == date(1995, 1, 7)
    assert parse_birthdate("January 7th 1995") == date(1995, 1, 7)


def test_parse_dmy_with_dashes():
    assert parse_birthdate("07-01-1995") == date(1995, 1, 7)


def test_parse_dmy_with_slashes():
    assert parse_birthdate("7/1/1995") == date(1995, 1, 7)


def test_parse_returns_none_for_no_year():
    # "7 Januari" without year should NOT be guessable
    assert parse_birthdate("7 Januari") is None


def test_parse_returns_none_for_garbage():
    assert parse_birthdate("nothing here") is None
    assert parse_birthdate("") is None
    assert parse_birthdate(None) is None


def test_parse_handles_indonesian_short_months():
    assert parse_birthdate("7 Jan 1995") == date(1995, 1, 7)
    assert parse_birthdate("7 Des 1995") == date(1995, 12, 7)


def test_parse_handles_lowercase_month():
    assert parse_birthdate("7 januari 1995") == date(1995, 1, 7)


def test_parse_rejects_invalid_date():
    # Feb 30 doesn't exist
    assert parse_birthdate("30 Februari 1995") is None


# ---------------------------------------------------------------------------
# parse_client_local_date
# ---------------------------------------------------------------------------


def test_local_time_iso_preferred():
    d = parse_client_local_date({"local_time_iso": "2026-05-18T13:17:00+07:00"})
    assert d == date(2026, 5, 18)


def test_local_date_explicit():
    d = parse_client_local_date({"local_date": "2026-05-18"})
    assert d == date(2026, 5, 18)


def test_local_time_alt_key():
    d = parse_client_local_date({"local_time": "2026-05-18T13:17:00Z"})
    assert d == date(2026, 5, 18)


def test_local_date_missing_returns_none():
    assert parse_client_local_date({}) is None
    assert parse_client_local_date(None) is None
    assert parse_client_local_date({"timezone": "Asia/Jakarta"}) is None


def test_local_date_handles_object_with_model_dump():
    class FakeCtx:
        def model_dump(self):
            return {"local_time_iso": "2026-05-18T13:17:00+07:00"}
    d = parse_client_local_date(FakeCtx())
    assert d == date(2026, 5, 18)


# ---------------------------------------------------------------------------
# calculate_age
# ---------------------------------------------------------------------------


def test_age_jan_7_1995_on_may_18_2026_is_31():
    """Canonical regression — the bug that prompted this work."""
    assert calculate_age(date(1995, 1, 7), date(2026, 5, 18)) == 31


def test_age_same_day_increments():
    # On birthday itself → age increments
    assert calculate_age(date(1995, 1, 7), date(2026, 1, 7)) == 31


def test_age_day_before_birthday_not_yet():
    assert calculate_age(date(1995, 1, 7), date(2026, 1, 6)) == 30


def test_age_birthdate_in_future_negative_not_calculated():
    # We don't guard for this in the service (caller's job to provide sane data)
    # but ensure the arithmetic is consistent.
    assert calculate_age(date(2030, 1, 7), date(2026, 5, 18)) == -4


# ---------------------------------------------------------------------------
# format_birthday — bilingual rendering
# ---------------------------------------------------------------------------


def test_format_birthday_indonesian():
    fmt = format_birthday(date(1995, 1, 7))
    assert fmt["id"] == "7 Januari 1995"


def test_format_birthday_english():
    fmt = format_birthday(date(1995, 1, 7))
    assert fmt["en"] == "January 7, 1995"


def test_format_birthday_iso():
    fmt = format_birthday(date(1995, 1, 7))
    assert fmt["iso"] == "1995-01-07"


# ---------------------------------------------------------------------------
# render_profile_runtime_context — full integration
# ---------------------------------------------------------------------------


def test_render_full_context_with_age():
    block = render_profile_runtime_context(
        {"profile": {"birthday": "1995-01-07"}},
        {"local_time_iso": "2026-05-18T13:17:00+07:00", "timezone": "Asia/Jakarta"},
    )
    assert "User current age: 31" in block
    assert "1995-01-07" in block
    assert "7 Januari 1995" in block
    assert "January 7, 1995" in block
    assert "Do NOT recalculate" in block


def test_render_handles_human_readable_birthday_value():
    """Even if profile.birthday is stored as '7 Januari 1995' (legacy), parse + render."""
    block = render_profile_runtime_context(
        {"profile": {"birthday": "7 Januari 1995"}},
        {"local_time_iso": "2026-05-18T13:17:00+07:00"},
    )
    assert "31" in block
    assert "1995-01-07" in block, "should normalize to ISO in the rendered block"


def test_render_empty_when_no_birthday():
    block = render_profile_runtime_context({"profile": {}}, {"local_time_iso": "2026-05-18"})
    assert block == ""


def test_render_handles_missing_local_date():
    """No local_time_iso → render birthday but no age."""
    block = render_profile_runtime_context(
        {"profile": {"birthday": "1995-01-07"}},
        {},
    )
    assert "1995-01-07" in block
    assert "do not state" in block.lower()
    assert "User current age" not in block


def test_render_handles_unparsable_birthday():
    block = render_profile_runtime_context(
        {"profile": {"birthday": "sometime in the 90s"}},
        {"local_time_iso": "2026-05-18T13:17:00+07:00"},
    )
    assert "unparsed" in block.lower()
    assert "User current age" not in block


def test_render_accepts_alt_profile_keys():
    """date_of_birth, dob, birthdate all work."""
    for key in ("date_of_birth", "dob", "birthdate"):
        block = render_profile_runtime_context(
            {"profile": {key: "1995-01-07"}},
            {"local_time_iso": "2026-05-18T13:17:00+07:00"},
        )
        assert "31" in block, f"failed for key {key}"


def test_render_accepts_none_identity():
    assert render_profile_runtime_context(None, {"local_time_iso": "2026-05-18"}) == ""


# ---------------------------------------------------------------------------
# Inline runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    failed: list[str] = []
    passed = 0
    for name, obj in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(obj):
            try:
                obj()
                print(f"  PASS  {name}")
                passed += 1
            except Exception as exc:
                import traceback
                print(f"  FAIL  {name}: {exc}")
                traceback.print_exc()
                failed.append(name)
    print(f"\n{passed} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)
