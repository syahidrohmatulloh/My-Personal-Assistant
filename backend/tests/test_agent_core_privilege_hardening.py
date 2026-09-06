from pathlib import Path


SCHEMA = Path(
    "schema_phase426_agent_core_least_privilege.sql"
).read_text(encoding="utf-8").lower()


def test_authenticated_agent_core_access_remains_read_only() -> None:
    for table in (
        "agent_objectives",
        "agent_plans",
        "agent_plan_steps",
        "agent_events",
    ):
        assert f"grant select on public.{table}" in SCHEMA

    assert "grant insert" not in SCHEMA.split(
        "to authenticated;"
    )[0]


def test_service_role_has_no_hard_delete_or_truncate_grant() -> None:
    assert "grant delete" not in SCHEMA
    assert "grant truncate" not in SCHEMA


def test_agent_events_is_append_only_for_service_role() -> None:
    assert (
        "grant select, insert\n"
        "on public.agent_events\n"
        "to service_role;"
        in SCHEMA
    )

    assert (
        "grant select, insert, update\n"
        "on public.agent_events"
        not in SCHEMA
    )


def test_mutable_agent_state_allows_update_not_delete() -> None:
    for table in (
        "agent_objectives",
        "agent_plans",
        "agent_plan_steps",
    ):
        assert (
            "grant select, insert, update\n"
            f"on public.{table}\n"
            "to service_role;"
            in SCHEMA
        )
