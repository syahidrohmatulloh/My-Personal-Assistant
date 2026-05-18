"""Smoke tests for the user_mood service.

No DB / Supabase required — we test pure-Python logic by injecting fake row
data into the helper functions directly.

Run:
    cd backend && python -m pytest tests/test_user_mood.py -v
or just:
    cd backend && python tests/test_user_mood.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sys
from pathlib import Path

# Allow running this file directly without pytest. Add backend/ to path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import user_mood
from app.services.user_mood_prompt import render_user_mood_block


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_ago(n: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=n)).isoformat()


def _days_ago(n: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# Causal extraction
# ---------------------------------------------------------------------------


def test_extract_causal_indonesian():
    rows = [
        {"note": "lagi capek banget karena meeting non-stop seharian"},
        {"note": "happy karena Putri kasih kabar baik"},
    ]
    causes = user_mood._extract_causal(rows)
    assert any("meeting" in c.lower() for c in causes), causes
    assert any("putri kasih kabar baik" in c.lower() for c in causes), causes


def test_extract_causal_english():
    rows = [
        {"note": "feeling drained because of the deadline crunch this week"},
    ]
    causes = user_mood._extract_causal(rows)
    assert any("deadline" in c.lower() for c in causes), causes


def test_extract_causal_empty_returns_empty():
    rows = [{"note": "feeling ok today"}, {"note": None}]
    causes = user_mood._extract_causal(rows)
    # No "karena"/"because" markers present
    assert causes == [], causes


def test_extract_causal_includes_tags():
    rows = [{"note": "blah blah", "tags": ["work_stress", "no_sleep"]}]
    causes = user_mood._extract_causal(rows)
    assert "#work_stress" in causes, causes
    assert "#no_sleep" in causes, causes


def test_extract_causal_deduplicates():
    rows = [
        {"note": "stressed because of work"},
        {"note": "still stressed because of work"},
    ]
    causes = user_mood._extract_causal(rows)
    # "work" should appear only once
    work_count = sum(1 for c in causes if "work" in c.lower() and not c.startswith("#"))
    assert work_count == 1, causes


# ---------------------------------------------------------------------------
# Latest snapshot
# ---------------------------------------------------------------------------


def test_latest_uses_most_recent_per_axis():
    """Latest row has only mood. Need to fall through to next row for energy."""
    rows = [
        {"mood": 2, "energy": None, "stress": None, "observed_at": _hours_ago(1)},
        {"mood": -1, "energy": 3, "stress": 1, "observed_at": _hours_ago(24)},
    ]
    latest = user_mood._build_latest(rows)
    assert latest["mood"] == 2.0
    assert latest["energy"] == 3.0
    assert latest["stress"] == 1.0


def test_latest_caps_at_3_rows():
    """Should not pull energy from row 4+, even if it's the only non-null one."""
    rows = [
        {"mood": 1, "energy": None, "stress": None, "observed_at": _hours_ago(1)},
        {"mood": None, "energy": None, "stress": None, "observed_at": _hours_ago(24)},
        {"mood": None, "energy": None, "stress": None, "observed_at": _hours_ago(48)},
        {"mood": None, "energy": 5, "stress": None, "observed_at": _hours_ago(72)},
    ]
    latest = user_mood._build_latest(rows)
    assert latest["energy"] is None, "should not coalesce across stale data"


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def test_baseline_requires_min_entries():
    rows = [
        {"mood": 1, "energy": 1, "stress": 1},
        {"mood": 2, "energy": 2, "stress": 2},
    ]
    baseline, n = user_mood._build_baseline(rows)
    assert baseline is None
    assert n == 2


def test_baseline_computes_mean():
    rows = [
        {"mood": 0, "energy": 0, "stress": 0},
        {"mood": 2, "energy": 2, "stress": 2},
        {"mood": -2, "energy": -2, "stress": -2},
    ]
    baseline, n = user_mood._build_baseline(rows)
    assert baseline is not None
    assert baseline["mood"] == 0.0
    assert baseline["energy"] == 0.0
    assert n == 3


# ---------------------------------------------------------------------------
# Delta
# ---------------------------------------------------------------------------


def test_delta_labels_above_threshold():
    latest = {"mood": 3.0, "energy": 0.0, "stress": -2.0}
    baseline = {"mood": 0.0, "energy": 0.0, "stress": 0.0}
    delta = user_mood._build_delta(latest, baseline)
    assert delta["label_mood"] == "higher than usual"
    assert delta["label_energy"] == "near baseline"
    assert delta["label_stress"] == "lower than usual"


def test_delta_near_baseline_when_under_threshold():
    latest = {"mood": 0.5, "energy": -0.5, "stress": 0.3}
    baseline = {"mood": 0.0, "energy": 0.0, "stress": 0.0}
    delta = user_mood._build_delta(latest, baseline)
    assert delta["label_mood"] == "near baseline"
    assert delta["label_energy"] == "near baseline"
    assert delta["label_stress"] == "near baseline"


# ---------------------------------------------------------------------------
# Chat-message keyword detection
# ---------------------------------------------------------------------------


def test_chat_detection_indonesian_tired():
    sig = user_mood._detect_chat_message_mood("aku capek banget hari ini")
    assert sig is not None
    assert sig["mood_hint"] == "tired"
    assert "capek banget" in sig["matched_keywords"]


def test_chat_detection_english_stressed():
    sig = user_mood._detect_chat_message_mood("I'm so overwhelmed with this project")
    assert sig is not None
    assert sig["mood_hint"] == "stressed"


def test_chat_detection_no_match_returns_none():
    sig = user_mood._detect_chat_message_mood("apa kabar")
    assert sig is None


def test_chat_detection_priority_order():
    """When multiple moods match, negative ones win (tired > happy)."""
    sig = user_mood._detect_chat_message_mood("happy banget tapi capek banget")
    assert sig is not None
    assert sig["mood_hint"] == "tired"


def test_chat_detection_empty_message():
    assert user_mood._detect_chat_message_mood("") is None
    assert user_mood._detect_chat_message_mood(None) is None
    assert user_mood._detect_chat_message_mood("xx") is None


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def test_confidence_high_with_recent_data():
    rows = [
        {"confidence": 1.0, "observed_at": _hours_ago(2)},
        {"confidence": 1.0, "observed_at": _hours_ago(20)},
        {"confidence": 1.0, "observed_at": _days_ago(2)},
    ] * 4  # 12 rows
    conf = user_mood._compute_confidence(rows, sample_size=12)
    assert conf > 0.8, conf


def test_confidence_low_with_stale_data():
    rows = [
        {"confidence": 1.0, "observed_at": _days_ago(10)},
    ]
    conf = user_mood._compute_confidence(rows, sample_size=1)
    assert conf < 0.5, conf


def test_confidence_zero_with_no_rows():
    assert user_mood._compute_confidence([], 0) == 0.0


# ---------------------------------------------------------------------------
# Render — end-to-end with synthetic ctx
# ---------------------------------------------------------------------------


def test_render_returns_none_for_no_data():
    assert render_user_mood_block({"has_data": False}) is None
    assert render_user_mood_block(None) is None


def test_render_includes_required_sections():
    ctx = {
        "has_data": True,
        "latest": {
            "mood": -2.0,
            "energy": -1.0,
            "stress": 3.0,
            "note": "capek banget karena meeting",
            "observed_at": _hours_ago(2),
        },
        "baseline": {"mood": 0.0, "energy": 1.0, "stress": 0.5},
        "delta": {
            "mood": -2.0, "label_mood": "lower than usual",
            "energy": -2.0, "label_energy": "lower than usual",
            "stress": 2.5, "label_stress": "higher than usual",
        },
        "causal": ["meeting non-stop", "#work_stress"],
        "evidence": [_hours_ago(2)[:10] + ": capek banget karena meeting"],
        "confidence": 0.78,
        "sample_size": 8,
        "current_message_signal": {
            "mood_hint": "tired",
            "confidence": 0.6,
            "matched_keywords": ["capek banget"],
        },
    }
    block = render_user_mood_block(ctx)
    assert block is not None
    # Critical: clearly labeled as USER mood, not companion
    assert "User mood" in block
    # Must explicitly separate from companion mood
    assert "separate from your own companion mood" in block
    # Must include the no-label rule
    assert "Never recite this state back" in block
    # Includes baseline
    assert "30-day baseline" in block
    # Includes causal
    assert "meeting non-stop" in block
    # Includes tone hint
    assert "tired" in block


def test_render_omits_baseline_when_too_few_samples():
    ctx = {
        "has_data": True,
        "latest": {"mood": -1.0, "energy": None, "stress": None, "tags": []},
        "baseline": {},
        "delta": {},
        "causal": [],
        "evidence": [],
        "confidence": 0.4,
        "sample_size": 1,
        "current_message_signal": None,
    }
    block = render_user_mood_block(ctx)
    assert block is not None
    assert "30-day baseline" not in block, "should hide baseline with too few samples"
    assert "User mood" in block


def test_render_only_chat_signal_no_history():
    """User has zero self-reports but said 'aku capek banget' in chat."""
    ctx = {
        "has_data": True,
        "current_message_signal": {
            "mood_hint": "tired",
            "confidence": 0.6,
            "matched_keywords": ["capek banget"],
        },
    }
    block = render_user_mood_block(ctx)
    assert block is not None
    assert "tired" in block
    assert "30-day baseline" not in block


if __name__ == "__main__":
    # Run inline without pytest
    import inspect
    failed: list[str] = []
    passed = 0
    for name, obj in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(obj):
            try:
                obj()
                print(f"  PASS  {name}")
                passed += 1
            except Exception as exc:
                print(f"  FAIL  {name}: {exc}")
                failed.append(name)
    print(f"\n{passed} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)
