import pytest

from app.services import agent_core


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("proposed", "active"),
        ("active", "waiting"),
        ("waiting", "active"),
        ("active", "paused"),
        ("paused", "active"),
        ("active", "completed"),
        ("waiting", "completed"),
        ("active", "cancelled"),
        ("waiting", "cancelled"),
        ("paused", "cancelled"),
    ],
)
def test_objective_allowed_transitions(
    current: str,
    target: str,
) -> None:
    assert agent_core.objective_transition_allowed(
        current,
        target,
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("completed", "active"),
        ("cancelled", "active"),
        ("paused", "completed"),
        ("waiting", "paused"),
        ("active", "proposed"),
    ],
)
def test_objective_invalid_transitions_fail_closed(
    current: str,
    target: str,
) -> None:
    assert not agent_core.objective_transition_allowed(
        current,
        target,
    )

    with pytest.raises(
        agent_core.InvalidAgentTransition
    ):
        agent_core.require_objective_transition(
            current,
            target,
        )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "ready"),
        ("ready", "in_progress"),
        ("ready", "waiting"),
        ("ready", "blocked"),
        ("ready", "cancelled"),
        ("in_progress", "completed"),
        ("in_progress", "waiting"),
        ("in_progress", "blocked"),
        ("in_progress", "failed"),
        ("waiting", "ready"),
        ("blocked", "ready"),
        ("failed", "ready"),
        ("failed", "cancelled"),
    ],
)
def test_step_allowed_transitions(
    current: str,
    target: str,
) -> None:
    assert agent_core.step_transition_allowed(
        current,
        target,
    )


def test_completed_step_is_terminal() -> None:
    assert not agent_core.STEP_TRANSITIONS["completed"]
    assert not agent_core.STEP_TRANSITIONS["cancelled"]
