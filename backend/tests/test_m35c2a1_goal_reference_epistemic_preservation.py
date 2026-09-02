from app.services import goal_source_rules
from app.services import memory


def _decision():
    return goal_source_rules.GoalReferenceDecision(
        should_convert=True,
        reason="matched_active_goal",
        goal_id="goal-1",
        goal_title="Example goal",
        score=0.99,
    )


def test_goal_projection_preserves_explicit_user_provenance():
    row = {
        "content": "User has a goal",
        "kind": "context",
        "category": "goals",
        "confidence": 0.92,
        "source_priority": "explicit_user_statement",
        "last_confirmed_at": None,
    }

    converted = goal_source_rules.convert_row_to_goal_reference(
        row,
        _decision(),
    )

    assert converted["kind"] == "plan"
    assert converted["category"] == "goals"
    assert converted["structured_field"] == "active_goal_reference"

    assert converted["source_priority"] == "explicit_user_statement"
    assert converted["confidence"] == 0.92
    assert converted["last_confirmed_at"] is None


def test_goal_projection_does_not_upgrade_assistant_plan():
    row = {
        "content": "Assistant-originated plan",
        "kind": "plan",
        "category": "goals",
        "confidence": 0.54,
        "source_priority": "assistant_confirmation",
        "last_confirmed_at": None,
    }

    converted = goal_source_rules.convert_row_to_goal_reference(
        row,
        _decision(),
    )

    assert converted["source_priority"] == "assistant_confirmation"
    assert converted["confidence"] == 0.54
    assert converted["last_confirmed_at"] is None


def test_goal_projection_preserves_system_inference():
    row = {
        "content": "Deterministically derived goal reference",
        "kind": "context",
        "category": "goals",
        "confidence": 0.54,
        "source_priority": "system_inference",
        "last_confirmed_at": None,
    }

    converted = goal_source_rules.convert_row_to_goal_reference(
        row,
        _decision(),
    )

    assert converted["source_priority"] == "system_inference"
    assert converted["confidence"] == 0.54
    assert converted["last_confirmed_at"] is None


def test_m35c2a_legacy_plan_remains_low_confidence_after_goal_projection():
    mem = memory.ExtractedMemory(
        content="Concrete assistant plan",
        kind="plan",
        memory_key="example_goal",
        memory_value="example",
        category="goals",
        confidence=0.97,
    )

    row = {
        "content": mem.content,
        "kind": mem.kind,
        "category": mem.category,
        **memory._legacy_epistemic_fields(mem),
    }

    assert row["source_priority"] == "assistant_confirmation"
    assert row["confidence"] == 0.54

    converted = goal_source_rules.convert_row_to_goal_reference(
        row,
        _decision(),
    )

    assert converted["source_priority"] == "assistant_confirmation"
    assert converted["confidence"] == 0.54
    assert converted["last_confirmed_at"] is None


def test_projection_does_not_invent_epistemic_fields_when_absent():
    row = {
        "content": "Legacy row",
        "kind": "context",
        "category": "goals",
    }

    converted = goal_source_rules.convert_row_to_goal_reference(
        row,
        _decision(),
    )

    assert "source_priority" not in converted
    assert "confidence" not in converted
    assert "last_confirmed_at" not in converted
