
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.memory import rank_memory_rows, memory_retrieval_score, format_for_prompt


def test_superseded_memory_is_excluded():
    rows = [
        {"content": "Old birthday", "similarity": 0.99, "superseded": True},
        {"content": "Current birthday", "similarity": 0.70, "superseded": False},
    ]
    ranked = rank_memory_rows(rows)
    assert [r["content"] for r in ranked] == ["Current birthday"]


def test_structured_identity_can_beat_generic_similarity():
    generic = {
        "content": "Generic chat context",
        "similarity": 0.75,
        "kind": "context",
        "confidence": 0.60,
    }
    birthday = {
        "content": "User's birthday is January 7, 1995",
        "similarity": 0.64,
        "kind": "fact",
        "category": "important_dates",
        "structured_field": "birthday",
        "structured_value": "1995-01-07",
        "confidence": 0.98,
        "source_priority": "explicit_user_statement",
    }
    ranked = rank_memory_rows([generic, birthday])
    assert ranked[0]["content"] == birthday["content"]
    assert memory_retrieval_score(birthday) > memory_retrieval_score(generic)


def test_format_for_prompt_omits_superseded_and_includes_metadata():
    prompt = format_for_prompt([
        {
            "content": "User's birthday is January 7, 1995",
            "similarity": 0.90,
            "category": "important_dates",
            "structured_field": "birthday",
            "confidence": 0.98,
        },
        {"content": "Old duplicate", "similarity": 0.99, "superseded": True},
    ])
    assert "January 7, 1995" in prompt
    assert "Old duplicate" not in prompt
    assert "birthday" in prompt
    assert "confidence=0.98" in prompt
