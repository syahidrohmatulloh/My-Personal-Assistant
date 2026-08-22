import ast
import inspect
from pathlib import Path

from app.services import memory


def _memory_module_path() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "services" / "memory.py"


def test_memory_public_runtime_functions_are_not_shadowed() -> None:
    source = _memory_module_path().read_text(encoding="utf-8")
    tree = ast.parse(source)

    definitions: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions.setdefault(node.name, []).append(node.lineno)

    assert definitions.get("retrieve_relevant") == [565]
    assert definitions.get("format_for_prompt") == [608]

    assert "_legacy_retrieve_relevant_simple" in definitions
    assert "_legacy_format_for_prompt_simple" in definitions


def test_active_retrieve_relevant_uses_ranked_runtime_path() -> None:
    source = inspect.getsource(memory.retrieve_relevant)

    assert "rank_memory_rows(rows, min_similarity=min_similarity)" in source
    assert "match_count = min(max(limit * 4, limit), 32)" in source
    assert "gate_decision = should_retrieve_memory(query_text)" in source


def test_active_format_for_prompt_uses_ranked_memory_prompt() -> None:
    source = inspect.getsource(memory.format_for_prompt)

    assert "ranked = rank_memory_rows(memories)" in source
    assert "Use higher-confidence and structured memories first" in source
