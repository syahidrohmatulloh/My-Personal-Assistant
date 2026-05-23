from pathlib import Path

MEMORY_REVIEW = Path("app/routers/memory_review.py").read_text(encoding="utf-8")


def _calendar_list_block() -> str:
    start = MEMORY_REVIEW.index("async def list_calendar_candidates(")
    next_route = MEMORY_REVIEW.find("\n@router.", start + 1)
    end = next_route if next_route != -1 else len(MEMORY_REVIEW)
    return MEMORY_REVIEW[start:end]


def test_calendar_list_hides_pending_candidates_by_default():
    block = _calendar_list_block()

    assert "include_pending: bool = False" in block
    assert 'else "calendar_event_status.in.(confirmed_local,synced_google)"' in block
    assert '"calendar_candidate.eq.true,calendar_event_status.in.(confirmed_local,synced_google)"' in block


def test_calendar_route_documents_internal_pending_candidates():
    assert "Pending Calendar candidates are hidden by default" in MEMORY_REVIEW
    assert "chat confirmation accepts them" in MEMORY_REVIEW
