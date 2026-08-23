from pathlib import Path

SOURCE = Path("app/routers/memory_review.py").read_text(encoding="utf-8")


def _function_block(name: str) -> str:
    start = SOURCE.index(f"async def {name}(")
    next_route = SOURCE.find("\n@router.", start + 1)
    end = next_route if next_route != -1 else len(SOURCE)
    return SOURCE[start:end]


def test_memory_graph_view_endpoint_exists_as_post_not_get():
    assert "@router.post(\"/graph-view\")" in SOURCE
    assert "@router.get(\"/graph-view\")" not in SOURCE


def test_memory_graph_view_endpoint_is_auth_and_pin_gated():
    block = _function_block("memory_graph_view")

    assert "body: MemoryPinIn" in block
    assert "Depends(get_current_user_id)" in block
    assert "memory_pin.require_valid_pin(user_id=user_id, pin=body.pin)" in block


def test_memory_graph_view_endpoint_is_user_scoped_and_read_only():
    block = _function_block("memory_graph_view")

    assert ".table(\"memories\")" in block
    assert ".eq(\"user_id\", user_id)" in block
    assert "project_memory_rows(rows)" in block
    assert "build_memory_graph_view_model(" in block

    forbidden = [
        ".insert(",
        ".update(",
        ".upsert(",
        ".delete(",
        ".rpc(",
    ]
    for token in forbidden:
        assert token not in block


def test_memory_graph_view_endpoint_does_not_accept_pin_in_query_param():
    block = _function_block("memory_graph_view")

    assert "pin: str" not in block
    assert "pin =" not in block
    assert "pin=" not in block.replace("pin=body.pin", "")
