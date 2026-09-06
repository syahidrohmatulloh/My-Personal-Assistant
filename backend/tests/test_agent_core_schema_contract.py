from pathlib import Path


SCHEMA = Path(
    "schema_phase425_agent_core.sql"
).read_text(encoding="utf-8")


def test_agent_core_uses_four_separate_tables() -> None:
    for table in (
        "agent_objectives",
        "agent_plans",
        "agent_plan_steps",
        "agent_events",
    ):
        assert (
            f"create table if not exists public.{table}"
            in SCHEMA
        )


def test_agent_core_does_not_repurpose_existing_domains() -> None:
    forbidden = (
        "alter table public.memories",
        "alter table public.goals",
        "alter table public.calendar_pending_actions",
        "alter table public.proactive_nudges",
    )

    for statement in forbidden:
        assert statement not in SCHEMA.lower()


def test_agent_core_tables_enable_rls() -> None:
    for table in (
        "agent_objectives",
        "agent_plans",
        "agent_plan_steps",
        "agent_events",
    ):
        assert (
            f"alter table public.{table}\n"
            "    enable row level security;"
            in SCHEMA
        )


def test_direct_authenticated_mutation_is_not_granted() -> None:
    assert (
        "grant select on public.agent_objectives\n"
        "to authenticated;"
        in SCHEMA
    )

    assert (
        "grant all on public.agent_objectives\n"
        "to authenticated;"
        not in SCHEMA
    )

    assert (
        "from public, anon, authenticated;"
        in SCHEMA
    )


def test_atomic_rpc_contracts_exist() -> None:
    for function_name in (
        "agent_core_create_objective_v1",
        "agent_core_transition_objective_v1",
        "agent_core_transition_step_v1",
        "agent_core_verify_step_v1",
        "agent_core_record_event_v1",
    ):
        assert function_name in SCHEMA


def test_completion_requires_completed_verified_steps() -> None:
    assert "objective has incomplete plan steps" in SCHEMA
    assert "objective has unverified required steps" in SCHEMA


def test_no_autonomous_scheduler_added_by_schema() -> None:
    assert "cron" not in SCHEMA.lower()
    assert "scheduler" not in SCHEMA.lower()


def test_agent_core_canonical_audit_metadata_wins() -> None:
    canonical_right_hand_merge = (
        "coalesce(\n"
        "            p_evidence,\n"
        "            '{}'::jsonb\n"
        "        )\n"
        "        || jsonb_build_object("
    )

    assert SCHEMA.count(canonical_right_hand_merge) == 3

    unsafe_right_hand_evidence = (
        "jsonb_build_object(\n"
        "            'from_status'"
    )

    for position in (
        i
        for i in range(len(SCHEMA))
        if SCHEMA.startswith(
            unsafe_right_hand_evidence,
            i,
        )
    ):
        nearby = SCHEMA[position : position + 500]
        assert "|| coalesce(" not in nearby


def test_agent_core_creation_validates_owned_references() -> None:
    assert (
        "Agent Core goal does not belong to user"
        in SCHEMA
    )
    assert (
        "Agent Core source conversation does not belong to user"
        in SCHEMA
    )
    assert (
        "Agent Core source message does not belong to user"
        in SCHEMA
    )
