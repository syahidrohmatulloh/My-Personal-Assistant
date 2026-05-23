from pathlib import Path

MEMORY_REVIEW = Path("app/routers/memory_review.py").read_text(encoding="utf-8")


def _function_block(name: str) -> str:
    start = MEMORY_REVIEW.index(f"async def {name}(")
    next_route = MEMORY_REVIEW.find("\n@router.", start + 1)
    end = next_route if next_route != -1 else len(MEMORY_REVIEW)
    return MEMORY_REVIEW[start:end]


def test_calendar_draft_update_does_not_inherit_memory_pin():
    assert "class CalendarDraftUpdateIn(BaseModel):" in MEMORY_REVIEW
    assert "class CalendarDraftUpdateIn(MemoryPinIn):" not in MEMORY_REVIEW


def test_calendar_action_model_has_no_pin():
    assert "class CalendarActionIn(BaseModel):" in MEMORY_REVIEW
    action_block = MEMORY_REVIEW[
        MEMORY_REVIEW.index("class CalendarActionIn(BaseModel):"):
        MEMORY_REVIEW.index("class CalendarDraftUpdateIn(BaseModel):")
    ]
    assert "pin" not in action_block


def test_calendar_endpoints_do_not_require_pin_validation():
    for name in [
        "dismiss_calendar_candidate",
        "confirm_calendar_candidate_local_event",
        "update_calendar_candidate_draft",
        "sync_calendar_candidate_to_google",
        "archive_calendar_candidate",
    ]:
        block = _function_block(name)
        assert "memory_pin.require_valid_pin" not in block
        assert "pin=body.pin" not in block
