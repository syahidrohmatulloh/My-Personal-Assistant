import pytest

from app.services.memory_quality_resolve import build_quality_resolve_plan


def test_keep_one_archive_rest_plan():
    plan = build_quality_resolve_plan(
        action="keep_one_archive_rest",
        keep_memory_id="m1",
        archive_memory_ids=["m2", "m3", "m2"],
    )

    assert plan.action == "keep_one_archive_rest"
    assert plan.keep_memory_id == "m1"
    assert plan.archive_memory_ids == ["m2", "m3"]
    assert plan.all_memory_ids == ["m1", "m2", "m3"]


def test_archive_memory_plan():
    plan = build_quality_resolve_plan(
        action="archive_memory",
        keep_memory_id=None,
        archive_memory_ids=["m1", "m1", "m2"],
    )

    assert plan.action == "archive_memory"
    assert plan.keep_memory_id is None
    assert plan.archive_memory_ids == ["m1", "m2"]
    assert plan.all_memory_ids == ["m1", "m2"]


def test_keep_one_cannot_archive_kept_memory():
    with pytest.raises(ValueError):
        build_quality_resolve_plan(
            action="keep_one_archive_rest",
            keep_memory_id="m1",
            archive_memory_ids=["m1", "m2"],
        )


def test_keep_one_requires_keep_memory_id():
    with pytest.raises(ValueError):
        build_quality_resolve_plan(
            action="keep_one_archive_rest",
            keep_memory_id=None,
            archive_memory_ids=["m2"],
        )


def test_archive_memory_requires_archive_ids():
    with pytest.raises(ValueError):
        build_quality_resolve_plan(
            action="archive_memory",
            keep_memory_id=None,
            archive_memory_ids=[],
        )


def test_unsupported_action_rejected():
    with pytest.raises(ValueError):
        build_quality_resolve_plan(
            action="merge_memories",
            keep_memory_id="m1",
            archive_memory_ids=["m2"],
        )
