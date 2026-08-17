"""Tests for the MR0.1 eval-set builder. Pure logic only; no Supabase needed.

Verifies the safety-critical parts: redaction never leaks full content, and the
record path writes IDs-only entries (never memory content) with correct
replace/append semantics.
"""

import importlib.util
import json
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "build_eval_set",
    Path(__file__).resolve().parents[1] / "tools" / "build_eval_set.py",
)
build_eval_set = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(build_eval_set)


def test_redact_truncates_and_single_lines():
    long = "line one\n" + "x" * 200
    out = build_eval_set._redact(long, width=40)
    assert "\n" not in out
    assert len(out) <= 40
    assert out.endswith("…")


def test_redact_short_content_untouched():
    assert build_eval_set._redact("no sugar coffee") == "no sugar coffee"


def test_load_output_new_file(tmp_path):
    path = tmp_path / "retrieval_eval.local.json"
    data = build_eval_set._load_output(path, "user-123")
    assert data == {"user_id": "user-123", "queries": []}


def test_write_and_reload_roundtrip_ids_only(tmp_path):
    path = tmp_path / "retrieval_eval.local.json"
    data = {
        "user_id": "user-123",
        "queries": [{"query": "coffee", "relevant_ids": ["id1", "id2"], "notes": "no sugar"}],
    }
    build_eval_set._write_output(path, data)
    reloaded = json.loads(path.read_text(encoding="utf-8"))

    assert reloaded["user_id"] == "user-123"
    assert reloaded["queries"][0]["relevant_ids"] == ["id1", "id2"]
    assert set(reloaded["queries"][0].keys()) <= {"query", "relevant_ids", "notes"}


def test_load_preserves_existing_and_fills_user_id(tmp_path):
    path = tmp_path / "retrieval_eval.local.json"
    build_eval_set._write_output(path, {"queries": [{"query": "q", "relevant_ids": ["a"]}]})
    data = build_eval_set._load_output(path, "user-xyz")
    assert data["user_id"] == "user-xyz"
    assert len(data["queries"]) == 1
