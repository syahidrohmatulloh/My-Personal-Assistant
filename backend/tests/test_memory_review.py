from app.routers.memory_review import (
    _build_review_payload,
    _category_to_kind,
    _group_for_category,
)


def test_group_for_category_identity_structured_fields():
    assert _group_for_category("important_dates", "birthday") == "Identity"
    assert _group_for_category("preferences", "nickname") == "Identity"
    assert _group_for_category("identity", None) == "Identity"


def test_group_for_category_behavioral_pattern():
    assert (
        _group_for_category(
            "preferences",
            "debugging_support_style_under_frustration",
        )
        == "Behavioral Patterns"
    )


def test_category_to_kind_mapping():
    assert _category_to_kind("preferences") == "preference"
    assert _category_to_kind("goals") == "plan"
    assert _category_to_kind("constraints") == "context"
    assert _category_to_kind("important_dates") == "fact"


def test_build_review_payload_splits_active_and_archived():
    rows = [
        {
            "id": "m1",
            "content": "User's birthday is 1995-01-07",
            "category": "important_dates",
            "structured_field": "birthday",
            "structured_value": "1995-01-07",
            "superseded": False,
            "evidence": ["user said birthday"],
        },
        {
            "id": "m2",
            "content": "Old birthday",
            "category": "important_dates",
            "structured_field": "birthday",
            "structured_value": "7 Januari",
            "superseded": False,
            "archived": True,
            "status": "archived",
            "evidence": ["old"],
        },
        {
            "id": "m3",
            "content": "User prefers paste-ready commands",
            "category": "preferences",
            "structured_field": "debugging_support_style_under_frustration",
            "superseded": False,
            "evidence": ["debugging chat"],
        },
        {
            "id": "m4",
            "content": "Superseded correction history",
            "category": "preferences",
            "structured_field": "communication_preference",
            "superseded": True,
            "status": "superseded",
            "evidence": ["old corrected value"],
        },
    ]

    payload = _build_review_payload(rows)

    assert payload["counts"] == {"active": 2, "archived": 1, "total": 3}
    assert "Identity" in payload["active"]
    assert "Behavioral Patterns" in payload["active"]
    assert "Identity" in payload["archived"]



def test_edit_memory_model_requires_pin():
    from pydantic import ValidationError
    from app.routers.memory_review import MemoryEditIn

    body = MemoryEditIn(
        content="User prefers careful complete patches.",
        category="preferences",
        pin="123456",
    )

    assert body.pin == "123456"

    try:
        MemoryEditIn(
            content="User prefers careful complete patches.",
            category="preferences",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("MemoryEditIn should require pin")
