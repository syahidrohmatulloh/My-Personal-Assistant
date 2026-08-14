from app.services import calendar_draft_actions


def test_calendar_draft_action_ignores_memory_pipeline_update() -> None:
    text = (
        "Jadi next step-nya bukan ganti stack, tapi audit memory pipeline: "
        "save embed retrieve inject summarize review."
    )

    assert calendar_draft_actions.is_calendar_draft_action_request(text) is False


def test_calendar_draft_action_ignores_codebase_update() -> None:
    text = "Tolong update response ini dan revisi wording stack FastAPI Supabase Claude VoyageAI."

    assert calendar_draft_actions.is_calendar_draft_action_request(text) is False


def test_calendar_draft_action_allows_explicit_calendar_update() -> None:
    text = "Tolong update jadwal meeting besok jam 3 jadi jam 4."

    assert calendar_draft_actions.is_calendar_draft_action_request(text) is True


def test_calendar_draft_action_allows_explicit_calendar_delete() -> None:
    text = "Hapus agenda meeting besok pagi dari Calendar."

    assert calendar_draft_actions.is_calendar_draft_action_request(text) is True
