from pathlib import Path


ROUTER = Path(
    "app/routers/agent_core.py"
).read_text(encoding="utf-8")


def test_agent_core_router_is_authenticated() -> None:
    assert "get_current_user_id" in ROUTER
    assert 'prefix="/agent-core"' in ROUTER


def test_user_can_pause_resume_cancel_and_inspect() -> None:
    required = (
        '@router.get("/objectives")',
        '@router.get("/objectives/{objective_id}")',
        '@router.post("/objectives/{objective_id}/pause")',
        '@router.post("/objectives/{objective_id}/resume")',
        '@router.post("/objectives/{objective_id}/cancel")',
    )

    for route in required:
        assert route in ROUTER


def test_verification_and_observation_are_explicit_surfaces() -> None:
    assert '@router.post("/steps/{step_id}/verify")' in ROUTER
    assert (
        '@router.post("/objectives/{objective_id}/observations")'
        in ROUTER
    )
