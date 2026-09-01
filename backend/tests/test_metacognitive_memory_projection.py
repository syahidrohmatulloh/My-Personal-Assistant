import asyncio

from app.services import memory_intelligence
from app.services.memory_intelligence import CandidateMemory


def test_metacognitive_hold_blocks_inferred_candidate(
    monkeypatch,
) -> None:
    persisted = []

    async def fake_ask(_transcript):
        return [
            CandidateMemory(
                content="User probably prefers concise replies",
                category="preferences",
                source_priority="repeated_pattern",
                confidence=0.95,
                evidence=["pattern"],
            )
        ]

    async def fake_persist(**kwargs):
        persisted.append(kwargs["cand"])
        return {"saved": True}

    monkeypatch.setattr(
        memory_intelligence,
        "_ask_haiku",
        fake_ask,
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_persist_candidate",
        fake_persist,
    )

    audit = asyncio.run(
        memory_intelligence.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {
                    "role": "user",
                    "content": "maybe keep it short",
                }
            ],
            projection_posture="hold_for_confirmation",
        )
    )

    assert audit["saved"] == 0
    assert audit["skipped"] == 1
    assert persisted == []


def test_metacognitive_hold_keeps_explicit_user_fact_eligible(
    monkeypatch,
) -> None:
    persisted = []

    async def fake_ask(_transcript):
        return [
            CandidateMemory(
                content="User prefers concise replies",
                category="preferences",
                source_priority="explicit_user_statement",
                confidence=0.95,
                evidence=["I prefer concise replies"],
            )
        ]

    async def fake_persist(**kwargs):
        persisted.append(kwargs["cand"])
        return {"saved": True}

    monkeypatch.setattr(
        memory_intelligence,
        "_ask_haiku",
        fake_ask,
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_persist_candidate",
        fake_persist,
    )

    audit = asyncio.run(
        memory_intelligence.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {
                    "role": "user",
                    "content": "I prefer concise replies",
                }
            ],
            projection_posture="hold_for_confirmation",
        )
    )

    assert audit["saved"] == 1
    assert audit["skipped"] == 0
    assert len(persisted) == 1
    assert (
        persisted[0].source_priority
        == "explicit_user_statement"
    )


def test_eligible_projection_allows_repeated_pattern(
    monkeypatch,
) -> None:
    persisted = []

    async def fake_ask(_transcript):
        return [
            CandidateMemory(
                content="User prefers concise replies",
                category="preferences",
                source_priority="repeated_pattern",
                confidence=0.95,
                evidence=["pattern"],
            )
        ]

    async def fake_persist(**kwargs):
        persisted.append(kwargs["cand"])
        return {"saved": True}

    monkeypatch.setattr(
        memory_intelligence,
        "_ask_haiku",
        fake_ask,
    )
    monkeypatch.setattr(
        memory_intelligence,
        "_persist_candidate",
        fake_persist,
    )

    audit = asyncio.run(
        memory_intelligence.extract_and_persist(
            user_id="u1",
            conversation_id="c1",
            recent_messages=[
                {
                    "role": "user",
                    "content": "keep it short again",
                }
            ],
            projection_posture="eligible",
        )
    )

    assert audit["saved"] == 1
    assert len(persisted) == 1
