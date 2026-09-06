from pathlib import Path


RUNTIME = Path(
    "app/services/cognitive_runtime.py"
).read_text(encoding="utf-8")

CHAT = Path(
    "app/routers/chat.py"
).read_text(encoding="utf-8")

CONTEXT = Path(
    "app/services/cognitive_turn_context.py"
).read_text(encoding="utf-8")

MAIN = Path(
    "app/main.py"
).read_text(encoding="utf-8")


def test_cognitive_runtime_owns_agent_core_orchestration() -> None:
    assert "from app.services import agent_core" in RUNTIME
    assert (
        "from app.services import agent_core_intelligence"
        in RUNTIME
    )
    assert "agent_core_snapshot" in RUNTIME
    assert "retrieve_agent_core_snapshot" in RUNTIME
    assert "maybe_activate_agent_objective" in RUNTIME


def test_chat_uses_runtime_not_direct_agent_core_service() -> None:
    assert (
        "_cognitive_runtime.maybe_activate_agent_objective"
        in CHAT
    )
    assert (
        "_cognitive_runtime.retrieve_agent_core_snapshot"
        in CHAT
    )
    assert "from app.services import agent_core" not in CHAT
    assert (
        "from app.services import agent_core_intelligence"
        not in CHAT
    )


def test_agent_core_context_enters_model_context() -> None:
    assert "agent_core_context" in CONTEXT
    assert (
        'volatile_context += "\\n\\n" + agent_core_context'
        in CONTEXT
    )


def test_goal_background_projection_is_suppressed_on_objective_creation() -> None:
    assert "agent_objective_created" in CHAT
    assert "not agent_objective_created" in CHAT


def test_agent_core_router_registered_without_scheduler() -> None:
    assert "agent_core," in MAIN
    assert "app.include_router(agent_core.router)" in MAIN
    assert "start_agent_core" not in MAIN
    assert "stop_agent_core" not in MAIN


def test_cognitive_runtime_version_remains_frozen() -> None:
    assert (
        'COGNITIVE_RUNTIME_VERSION = "M31D-v1"'
        in RUNTIME
    )
