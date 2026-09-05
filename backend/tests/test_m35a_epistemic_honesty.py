from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from app.services import memory_intelligence
from app.services import memory_lifecycle_governance
from app.services import metacognitive_policy
from app.services import mood_memory_feedback
from app.services import relationship_memory


def _trust(row):
    return metacognitive_policy._assess_evidence(
        [row],
        now=datetime.now(timezone.utc),
    )


def test_system_inference_is_canonical_and_llm_cannot_self_assign_it():
    assert "system_inference" in get_args(
        memory_intelligence.SourcePriority
    )
    assert (
        memory_intelligence.SYSTEM_INFERENCE_SAVE_THRESHOLD
        == 0.50
    )
    assert (
        memory_intelligence.MAX_SYSTEM_INFERENCE_CONFIDENCE
        == 0.54
    )
    assert (
        memory_intelligence._SAVE_THRESHOLDS["system_inference"]
        == 0.50
    )

    # Deterministic runtime code may assign this provenance.
    # The extraction LLM must not be offered this label.
    assert (
        '"system_inference"'
        not in memory_intelligence._EXTRACTION_SYSTEM_PROMPT
    )


def test_relationship_rule_inference_is_unverified_end_to_end():
    candidates = relationship_memory.build_relationship_memory_candidates(
        user_message=(
            "tolong patch final yang lebih teliti dan menyeluruh, "
            "jangan nebak kalau ada error build"
        ),
        assistant_response="",
    )
    assert candidates

    row = {
        **candidates[0].as_memory_payload("u"),
        "id": "r1",
    }

    assert row["source_priority"] == "system_inference"
    assert row["confidence"] <= 0.54
    assert row["last_confirmed_at"] is None

    life = memory_lifecycle_governance.assess_memory_lifecycle(row)
    assert life.needs_confirmation is True
    assert life.confirmed is False

    trust, refs = _trust(row)
    assert trust == "unverified"
    assert refs == ("r1",)


def test_mood_rule_inference_is_unverified_end_to_end():
    candidate = mood_memory_feedback.build_behavioral_memory_candidate(
        user_message=(
            "aku capek error ini, "
            "tolong langsung kasih command patch"
        ),
        assistant_response="cd backend && pytest -q",
        user_mood_context=None,
    )
    assert candidate is not None

    row = {
        **candidate.as_memory_payload("u"),
        "id": "m1",
    }

    assert row["source_priority"] == "system_inference"
    assert row["confidence"] <= 0.54
    assert row["last_confirmed_at"] is None

    life = memory_lifecycle_governance.assess_memory_lifecycle(row)
    assert life.needs_confirmation is True
    assert life.confirmed is False

    trust, refs = _trust(row)
    assert trust == "unverified"
    assert refs == ("m1",)


def test_explicit_user_memory_remains_trusted_without_canonical_confirmation():
    row = {
        "id": "e1",
        "content": "User explicitly prefers concise answers.",
        "confidence": 0.90,
        "source_priority": "explicit_user_statement",
        # Historical metadata must not become canonical confirmation.
        "last_confirmed_at": (
            datetime.now(timezone.utc).isoformat()
        ),
        "superseded": False,
    }

    life = memory_lifecycle_governance.assess_memory_lifecycle(row)

    # Direct-user provenance is already strong enough to trust, while
    # confirmation remains a separate canonical user action/state.
    assert life.needs_confirmation is False
    assert life.confirmed is False

    trust, refs = _trust(row)
    assert trust == "trusted"
    assert refs == ()


def test_inference_writers_never_synthesize_confirmation_timestamp():
    for rel_path in (
        "app/services/relationship_memory.py",
        "app/services/mood_memory_feedback.py",
    ):
        source = Path(rel_path).read_text(encoding="utf-8")

        assert '"last_confirmed_at": now' not in source
        assert "datetime.now(timezone.utc)" not in source
        assert '"last_confirmed_at": None' in source
