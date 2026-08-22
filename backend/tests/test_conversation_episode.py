from app.services.conversation_episode import (
    classify_episode_text,
    classify_summary_episode,
    episode_match_bonus,
)


def test_classify_episode_text_detects_core_routes() -> None:
    assert classify_episode_text("jangan overthinking").kind == "self_regulation"
    assert classify_episode_text("siapa nama anakku?").kind == "identity_family"
    assert classify_episode_text("deploy backend fly.io").kind == "dev_project"
    assert classify_episode_text("email nasabah Bank Mandiri").kind == "work_client"
    assert classify_episode_text("hotel melbourne visa").kind == "travel"
    assert classify_episode_text("cuaca besok di jakarta").kind == "calendar_schedule"


def test_episode_match_bonus_rewards_matching_summary_episode() -> None:
    row = {
        "title": "Family notes",
        "summary": "The user discussed Zahra and school planning.",
        "similarity": 0.2,
    }

    assert episode_match_bonus(query_text="siapa nama anakku?", summary_row=row) == 0.45
    assert episode_match_bonus(query_text="deploy backend", summary_row=row) == 0.0


def test_classify_summary_episode_uses_title_and_summary() -> None:
    row = {
        "title": "Aliyya backend work",
        "summary": "They discussed FastAPI, Supabase, and Fly.io deploys.",
    }

    assert classify_summary_episode(row).kind == "dev_project"
