from app.services import calendar_decision_router
from app.services.calendar_decision_router import CalendarDecision
from pathlib import Path


CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")
ROUTER = Path("app/services/calendar_decision_router.py").read_text(encoding="utf-8")
ACTIONS = Path("app/services/calendar_confirmation_actions.py").read_text(encoding="utf-8")


def test_calendar_decision_router_uses_llm_not_phrase_matcher():
    assert "SYSTEM_PROMPT" in ROUTER
    assert "Use semantic understanding, not keyword matching." in ROUTER
    assert "iya masukin" not in ROUTER
    assert "nggak usah" not in ROUTER


def test_calendar_decision_router_allowed_actions_and_threshold():
    assert "ALLOWED_ACTIONS" in ROUTER
    assert "accept_local" in ROUTER
    assert "accept_google" in ROUTER
    assert "dismiss" in ROUTER
    assert "MIN_CONFIDENCE_TO_EXECUTE" in ROUTER


def test_should_execute_decision_requires_safe_action_target_and_confidence():
    assert calendar_decision_router.should_execute_decision(
        CalendarDecision(action="accept_local", target_memory_id="abc", confidence=0.91, reason="ok")
    )
    assert not calendar_decision_router.should_execute_decision(
        CalendarDecision(action="accept_local", target_memory_id=None, confidence=0.91, reason="missing target")
    )
    assert not calendar_decision_router.should_execute_decision(
        CalendarDecision(action="accept_local", target_memory_id="abc", confidence=0.2, reason="low")
    )
    assert not calendar_decision_router.should_execute_decision(
        CalendarDecision(action="none", target_memory_id="abc", confidence=0.99, reason="none")
    )


def test_calendar_confirmation_actions_execute_router_decisions():
    assert "classify_calendar_confirmation" in ACTIONS
    assert "_accept_pending_suggestion_local" in ACTIONS
    assert "_accept_pending_suggestion_to_google" in ACTIONS
    assert "_dismiss_pending_suggestion" in ACTIONS
    assert "llm_calendar_confirmation_dismissed" in ACTIONS


def test_chat_wires_llm_calendar_confirmation_router():
    assert "calendar_confirmation_actions," in CHAT
    assert "render_pending_calendar_confirmation_context" in CHAT
    assert "apply_calendar_confirmation_decision" in CHAT
    assert "Mau aku masukin ke Calendar?" in CHAT
