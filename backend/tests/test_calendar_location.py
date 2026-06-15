"""Calendar vNext — Structured Event Location.

Covers: deterministic extraction, candidate carry-through, persistence
wiring, update preserve/replace semantics, Google payloads (all builders),
API output, the Golf dengan Indosat / Rainbow Hills regression, backfill
parsing, and reminder-system separation.
"""

from pathlib import Path

from app.routers import memory_review
from app.services import calendar_draft_actions
from app.services.calendar_candidate_extractor import (
    _candidate_from_intent_draft,
    _extract_location_hint,
)
from app.services.google_calendar_payload import build_google_event_body, next_iso_date

import sys

sys.path.insert(0, str(Path("tools").resolve().parent))
from tools import backfill_calendar_event_locations as backfill_tool
from tools.backfill_calendar_event_locations import derive_location


GOLF_MESSAGE = (
    "sayang aku mau kasih tau kamu, hari Minggu (14 Juni 2026) aku ada agenda "
    "golf di Rainbow Hills dengan Indosat, tee off jam 05.52"
)


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------

def test_location_hint_extracts_regression_case():
    assert _extract_location_hint(GOLF_MESSAGE) == "Rainbow Hills"


def test_location_hint_simple_indonesian_and_english():
    assert _extract_location_hint("sekarang padel di Parta Kuningan") == "Parta Kuningan"
    assert _extract_location_hint("dinner at Henshin with the finance team") == "Henshin"


def test_location_hint_rejects_days_people_and_deixis():
    assert _extract_location_hint("meeting di hari Senin sama tim") is None
    assert _extract_location_hint("makan siang dengan Budi") is None
    assert _extract_location_hint("ketemuan di sana jam 5") is None
    assert _extract_location_hint("janjian di situ nanti") is None
    assert _extract_location_hint("") is None
    assert _extract_location_hint(None) is None


# ---------------------------------------------------------------------------
# Candidate carries location (LLM draft first, deterministic fallback)
# ---------------------------------------------------------------------------

def test_intent_draft_location_is_preserved_on_candidate():
    candidate = _candidate_from_intent_draft(
        {
            "title": "Golf dengan Indosat",
            "event_date": "2026-06-14",
            "start_at": "2026-06-14T05:52:00+07:00",
            "end_at": "2026-06-14T06:52:00+07:00",
            "all_day": False,
            "location": "Rainbow Hills",
            "confidence": 0.9,
        },
        GOLF_MESSAGE,
    )

    assert candidate is not None
    assert candidate.title == "Golf dengan Indosat"
    assert candidate.location == "Rainbow Hills"
    assert "location Rainbow Hills" in candidate.structured_value
    assert candidate.content.endswith("at Rainbow Hills")


def test_intent_draft_without_location_falls_back_to_text_hint():
    candidate = _candidate_from_intent_draft(
        {
            "title": "Golf dengan Indosat",
            "event_date": "2026-06-14",
            "all_day": False,
            "location": None,
            "confidence": 0.8,
        },
        GOLF_MESSAGE,
    )

    assert candidate is not None
    assert candidate.location == "Rainbow Hills"


# ---------------------------------------------------------------------------
# Update semantics: omitted -> preserve, supplied -> replace
# ---------------------------------------------------------------------------

_UPDATE_TARGET = {
    "id": "abc",
    "calendar_event_title": "Golf dengan Indosat",
    "calendar_event_date": "2026-06-14",
    "calendar_event_start_at": "2026-06-14T05:52:00+07:00",
    "calendar_event_end_at": "2026-06-14T06:52:00+07:00",
    "calendar_event_all_day": False,
    "calendar_event_status": "confirmed_local",
    "calendar_event_location": "Rainbow Hills",
}


def test_update_without_location_preserves_existing_location():
    action = {
        "action": "update",
        "target_memory_id": "abc",
        "start_at": "2026-06-14T06:30:00+07:00",
        "end_at": "2026-06-14T07:30:00+07:00",
        "confidence": 0.9,
    }

    payload = calendar_draft_actions._build_update_payload(_UPDATE_TARGET, action)

    assert payload["calendar_event_location"] == "Rainbow Hills"
    assert "location=Rainbow Hills" in payload["structured_value"]
    assert payload["content"].endswith("at Rainbow Hills")
    assert payload["calendar_event_start_at"] == "2026-06-14T06:30:00+07:00"


def test_update_with_new_location_replaces_existing_location():
    action = {
        "action": "update",
        "target_memory_id": "abc",
        "location": "Pondok Indah Golf",
        "confidence": 0.9,
    }

    payload = calendar_draft_actions._build_update_payload(_UPDATE_TARGET, action)

    assert payload["calendar_event_location"] == "Pondok Indah Golf"
    assert "location=Pondok Indah Golf" in payload["structured_value"]
    assert "Rainbow Hills" not in payload["structured_value"]


def test_update_with_null_or_empty_location_preserves_existing():
    """This phase has no clearing: null, empty, and whitespace location
    values in an update must all preserve the stored location."""
    for noise in (None, "", "   "):
        action = {
            "action": "update",
            "target_memory_id": "abc",
            "location": noise,
            "event_date": "2026-06-15",
        }
        payload = calendar_draft_actions._build_update_payload(_UPDATE_TARGET, action)
        assert payload["calendar_event_location"] == "Rainbow Hills", f"noise={noise!r}"
        assert "location=Rainbow Hills" in payload["structured_value"]


def test_review_resolver_only_replaces_on_non_empty():
    resolve = memory_review._resolve_updated_location
    assert resolve(None, "Rainbow Hills") == "Rainbow Hills"      # omitted -> preserve
    assert resolve("", "Rainbow Hills") == "Rainbow Hills"        # empty -> preserve
    assert resolve("   ", "Rainbow Hills") == "Rainbow Hills"     # whitespace -> preserve
    assert resolve("Senayan City", "Rainbow Hills") == "Senayan City"  # new -> replace
    assert resolve(None, None) is None
    assert resolve("", None) is None


def test_update_target_without_location_stays_none():
    target = {**_UPDATE_TARGET, "calendar_event_location": None}
    action = {"action": "update", "target_memory_id": "abc", "event_date": "2026-06-15"}

    payload = calendar_draft_actions._build_update_payload(target, action)

    assert payload["calendar_event_location"] is None
    assert "location=" not in payload["structured_value"]


# ---------------------------------------------------------------------------
# Google Calendar payloads (all builders)
# ---------------------------------------------------------------------------

def test_shared_google_event_body_includes_location():
    body = build_google_event_body(
        title="Golf dengan Indosat",
        event_date="2026-06-14",
        description="Created by Aliyya from chat.",
        start_at="2026-06-14T05:52:00+07:00",
        end_at="2026-06-14T06:52:00+07:00",
        location="Rainbow Hills",
    )

    assert body["summary"] == "Golf dengan Indosat"
    assert body["location"] == "Rainbow Hills"
    assert body["start"] == {"dateTime": "2026-06-14T05:52:00+07:00"}
    assert body["end"] == {"dateTime": "2026-06-14T06:52:00+07:00"}


def test_shared_google_event_body_omits_empty_location():
    body = build_google_event_body(
        title="Golf dengan Indosat",
        event_date="2026-06-14",
        description="x",
        location="   ",
    )

    assert "location" not in body
    assert body["start"] == {"date": "2026-06-14"}
    assert body["end"] == {"date": "2026-06-15"}


def test_all_day_google_end_date_is_exclusive():
    """REGRESSION: Google's all-day end.date is exclusive — a one-day event
    on 2026-06-14 must end on 2026-06-15, never on the same date."""
    body = build_google_event_body(
        title="Family day",
        event_date="2026-06-14",
        description="x",
    )

    assert body["start"] == {"date": "2026-06-14"}
    assert body["end"] == {"date": "2026-06-15"}

    review_payload = memory_review._build_google_calendar_event_payload(
        title="Family day",
        event_date="2026-06-14",
        description="x",
    )
    assert review_payload["start"] == {"date": "2026-06-14"}
    assert review_payload["end"] == {"date": "2026-06-15"}


def test_next_iso_date_increments_and_survives_bad_input():
    assert next_iso_date("2026-06-14") == "2026-06-15"
    assert next_iso_date("2026-12-31") == "2027-01-01"
    assert next_iso_date("not-a-date") == "not-a-date"


def test_memory_review_google_payload_includes_location():
    payload = memory_review._build_google_calendar_event_payload(
        title="Golf dengan Indosat",
        event_date="2026-06-14",
        description="Created from memory review.",
        start_at="2026-06-14T05:52:00+07:00",
        end_at="2026-06-14T06:52:00+07:00",
        location="Rainbow Hills",
    )

    assert payload["location"] == "Rainbow Hills"


def test_memory_review_google_payload_without_location_has_no_field():
    payload = memory_review._build_google_calendar_event_payload(
        title="Golf dengan Indosat",
        event_date="2026-06-14",
        description="Created from memory review.",
    )

    assert "location" not in payload


# ---------------------------------------------------------------------------
# API output + edit contract
# ---------------------------------------------------------------------------

def test_normalize_calendar_candidate_exposes_location():
    normalized = memory_review._normalize_calendar_candidate(
        {
            "id": "abc",
            "calendar_event_status": "confirmed_local",
            "calendar_event_title": "Golf dengan Indosat",
            "calendar_event_date": "2026-06-14",
            "calendar_event_location": "Rainbow Hills",
        }
    )

    assert normalized["calendar_event_location"] == "Rainbow Hills"
    assert memory_review.CalendarCandidateOut(**{**normalized, "id": "abc"}).calendar_event_location == "Rainbow Hills"


def test_draft_update_model_accepts_location_and_defaults_to_none():
    body = memory_review.CalendarDraftUpdateIn(title="Golf dengan Indosat")
    assert body.location is None

    body = memory_review.CalendarDraftUpdateIn(location="Rainbow Hills")
    assert body.location == "Rainbow Hills"


def test_calendar_structured_value_includes_location():
    value = memory_review._calendar_structured_value(
        title="Golf dengan Indosat",
        event_date="2026-06-14",
        location="Rainbow Hills",
    )
    assert value.endswith("location=Rainbow Hills")


# ---------------------------------------------------------------------------
# Persistence wiring (source contracts, matching repo test style)
# ---------------------------------------------------------------------------

EXTRACTOR_SRC = Path("app/services/calendar_candidate_extractor.py").read_text(encoding="utf-8")
DRAFT_SRC = Path("app/services/calendar_draft_actions.py").read_text(encoding="utf-8")
CONFIRM_SRC = Path("app/services/calendar_confirmation_actions.py").read_text(encoding="utf-8")
REVIEW_SRC = Path("app/routers/memory_review.py").read_text(encoding="utf-8")


def test_candidate_insert_persists_location_column():
    assert '"calendar_event_location": candidate.location' in EXTRACTOR_SRC


def test_direct_google_create_persists_location_column():
    assert (
        '"calendar_event_location": location_text' in DRAFT_SRC
        or '"calendar_event_location": _clean_optional_text(draft.get("location"))' in DRAFT_SRC
    )


def test_confirmation_paths_preserve_location_column():
    assert CONFIRM_SRC.count('"calendar_event_location": row.get("calendar_event_location")') == 2
    assert "location=row.get(\"calendar_event_location\")" in CONFIRM_SRC


def test_review_select_lists_include_location():
    assert REVIEW_SRC.count("calendar_event_location") >= 8


def test_google_patch_paths_forward_location():
    assert 'location=payload.get("calendar_event_location")' in DRAFT_SRC
    assert "location=location," in REVIEW_SRC


# ---------------------------------------------------------------------------
# Backfill parser (legacy formats + regression case)
# ---------------------------------------------------------------------------

def test_backfill_parses_legacy_pipe_format():
    assert (
        derive_location("Golf | due_date=2026-06-14 | location=Rainbow Hills", None)
        == "Rainbow Hills"
    )


def test_backfill_parses_human_structured_format():
    assert (
        derive_location(
            "Calendar event: Golf dengan Indosat; date 2026-06-14; starts 2026-06-14T05:52:00+07:00; location Rainbow Hills",
            None,
        )
        == "Rainbow Hills"
    )


def test_backfill_parses_content_at_suffix():
    assert (
        derive_location(None, "User has a scheduled event: Golf dengan Indosat on 2026-06-14 at Rainbow Hills")
        == "Rainbow Hills"
    )


def test_backfill_regression_golf_conversational_blob():
    structured = (
        "Calendar event: sayang aku mau kasih tau kamu, hari Minggu (14 Juni 2026) "
        "aku ada agenda golf di Rainbow Hills dengan Indosat, tee off jam 05.52; date 2026-06-14"
    )
    assert derive_location(structured, None) == "Rainbow Hills"


def test_backfill_returns_none_when_nothing_derivable():
    assert derive_location("Calendar event: Standup; date 2026-06-15", "User has a scheduled event: Standup on 2026-06-15") is None


# ---------------------------------------------------------------------------
# Reminder separation
# ---------------------------------------------------------------------------

def test_backfill_tool_never_touches_reminders():
    tool_src = Path("tools/backfill_calendar_event_locations.py").read_text(encoding="utf-8")
    assert '.table("proactive_nudges")' not in tool_src
    assert tool_src.count('.table("memories")') == 2  # one select, one update
    assert tool_src.count('.update({"calendar_event_location"') == 1


def test_backfill_apply_is_guarded_against_concurrent_writes():
    tool_src = Path("tools/backfill_calendar_event_locations.py").read_text(encoding="utf-8")
    assert 'calendar_event_location.is.null,calendar_event_location.eq.' in tool_src


class _FakeBackfillQuery:
    def __init__(self, returned_rows):
        self.returned_rows = returned_rows
        self.operations = []

    def table(self, name):
        self.operations.append(("table", name))
        return self

    def update(self, payload):
        self.operations.append(("update", payload))
        return self

    def eq(self, field, value):
        self.operations.append(("eq", field, value))
        return self

    def or_(self, expression):
        self.operations.append(("or", expression))
        return self

    def select(self, fields):
        self.operations.append(("select", fields))
        return self

    def execute(self):
        from types import SimpleNamespace

        return SimpleNamespace(data=self.returned_rows)


def test_backfill_apply_counts_successful_guarded_update(monkeypatch):
    query = _FakeBackfillQuery([{"id": "row-1"}])

    def fake_safe_execute(operation):
        return operation(query)

    monkeypatch.setattr(backfill_tool, "safe_execute", fake_safe_execute)

    applied, skipped = backfill_tool.apply_backfills(
        [("row-1", "Golf dengan Indosat", "Rainbow Hills")]
    )

    assert (applied, skipped) == (1, 0)
    assert ("select", "id") in query.operations
    assert ("update", {"calendar_event_location": "Rainbow Hills"}) in query.operations


def test_backfill_apply_counts_concurrent_skip(monkeypatch):
    query = _FakeBackfillQuery([])

    def fake_safe_execute(operation):
        return operation(query)

    monkeypatch.setattr(backfill_tool, "safe_execute", fake_safe_execute)

    applied, skipped = backfill_tool.apply_backfills(
        [("row-1", "Golf dengan Indosat", "Rainbow Hills")]
    )

    assert (applied, skipped) == (0, 1)
    assert ("select", "id") in query.operations
