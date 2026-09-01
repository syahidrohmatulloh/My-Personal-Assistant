from pathlib import Path

ORCHESTRATION = Path(
    "app/services/cognitive_calendar_orchestration.py"
).read_text(encoding="utf-8")
HELPERS = Path(
    "app/services/chat_calendar_helpers.py"
).read_text(encoding="utf-8")
CONTEXT = Path(
    "app/services/cognitive_turn_context.py"
).read_text(encoding="utf-8")


def test_m34_is_authoritative_semantic_gate():
    assert "temporal_calendar_policy" in ORCHESTRATION
    assert "assess_calendar_semantics(" in ORCHESTRATION
    assert "should_check_pending_confirmation(" in ORCHESTRATION
    assert "requires_calendar_handling(" in HELPERS


def test_hard_gate_no_longer_uses_legacy_extractor_as_authority():
    function = HELPERS.split(
        "def should_hard_gate_calendar_candidate", 1
    )[1].split(
        "def render_calendar_hard_gate_clarification", 1
    )[0]
    assert "calendar_candidate_extractor" not in function
    assert "temporal_calendar_policy" in function


def test_generation_context_passes_current_message_to_pending_gate():
    assert "user_message=body.message" in CONTEXT
    assert "temporal_calendar_policy" in CONTEXT
    assert "assess_calendar_semantics(" in CONTEXT


def test_misleading_agenda_presupposition_is_removed():
    for source in (ORCHESTRATION, HELPERS, CONTEXT):
        assert "Ini kayaknya agenda" not in source
        assert "ini kayaknya agenda" not in source
