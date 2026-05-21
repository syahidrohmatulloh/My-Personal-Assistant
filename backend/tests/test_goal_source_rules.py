from app.services.goal_source_rules import (
    convert_row_to_goal_reference,
    decide_goal_reference,
)


def test_converts_duplicate_exercise_goal_to_reference():
    row = {
        "content": "User's goal is to be more consistent with exercise in 2026, training 2 hours per week with a personal trainer",
        "kind": "plan",
        "category": "goals",
    }
    goals = [
        {
            "id": "goal-123",
            "title": "Be more consistent with exercise in 2026",
            "description": "Training 2 hours per week with a personal trainer",
            "status": "active",
        }
    ]

    decision = decide_goal_reference(row, goals)

    assert decision.should_convert is True
    converted = convert_row_to_goal_reference(row, decision)
    assert converted["structured_field"] == "active_goal_reference"
    assert "goal-123" in converted["structured_value"]
    assert "exercise" in converted["content"].lower()


def test_does_not_convert_unrelated_memory():
    row = {
        "content": "User likes mangoes",
        "kind": "preference",
        "category": "preferences",
    }
    goals = [{"id": "goal-123", "title": "Exercise consistently", "status": "active"}]

    decision = decide_goal_reference(row, goals)

    assert decision.should_convert is False


def test_low_similarity_goalish_row_is_not_converted():
    row = {
        "content": "User has a goal to learn Japanese",
        "kind": "plan",
        "category": "goals",
    }
    goals = [{"id": "goal-123", "title": "Exercise consistently", "status": "active"}]

    decision = decide_goal_reference(row, goals)

    assert decision.should_convert is False
