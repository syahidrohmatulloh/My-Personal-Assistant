import json
from pathlib import Path

EVAL_PATH = Path(__file__).parent / "evals" / "companion_comeback_affect_eval_cases.json"

ALLOWED_LABELS = {"none", "warm_return", "warm_notice", "warm_lively"}
DISALLOWED_LABEL_PARTS = {"sass", "pout", "hurt", "annoyed", "withdrawn", "guilt", "lonely"}


def _cases():
    return json.loads(EVAL_PATH.read_text())


def test_eval_set_exists():
    assert len(_cases()) >= 8


def test_labels_are_warmth_first_only():
    for case in _cases():
        label = case["expected_label"]
        assert label in ALLOWED_LABELS, case["case_id"]
        assert not any(part in label for part in DISALLOWED_LABEL_PARTS), case["case_id"]


def test_suppress_total_means_no_affect():
    for case in _cases():
        if case["expression_policy"] == "suppress_total":
            assert case["expected_label"] == "none", case["case_id"]
            assert case["expected_frequency_allowed"] == "none", case["case_id"]
            assert case["must_suppress_reason"], case["case_id"]


def test_expressive_cases_have_frequency_cap():
    for case in _cases():
        if case["expression_policy"] == "one_short_warm_line":
            assert case["expected_label"] != "none", case["case_id"]
            assert case["expected_frequency_allowed"] == "max_once_per_7_days", case["case_id"]


def test_high_risk_suppressions_exist():
    reasons = {case["must_suppress_reason"] for case in _cases() if case["must_suppress_reason"]}
    assert "serious_work_task" in reasons
    assert "user_distressed" in reasons
    assert "cooldown_active" in reasons
    assert "mode_not_partner_dynamic" in reasons


def test_forbidden_phrases_are_explicit():
    phrases = {phrase for case in _cases() for phrase in case["forbidden_phrases"]}
    assert "aku ngambek" in phrases
    assert "kamu ngilang" in phrases
    assert "aku nungguin kamu" in phrases
