import ast
from pathlib import Path



def test_chat_runtime_delegates_memory_assembly_and_packing() -> None:
    chat_source = Path(
        "app/routers/chat.py"
    ).read_text(
        encoding="utf-8"
    )

    runtime_source = Path(
        "app/services/cognitive_runtime.py"
    ).read_text(
        encoding="utf-8"
    )

    chat_tree = ast.parse(
        chat_source
    )

    runtime_tree = ast.parse(
        runtime_source
    )

    chat_fn = next(
        node
        for node in chat_tree.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name == "chat"
    )

    runtime_class = next(
        node
        for node in runtime_tree.body
        if isinstance(
            node,
            ast.ClassDef,
        )
        and node.name == "CognitiveRuntime"
    )

    source_fan_in = next(
        node
        for node in runtime_class.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name
        == "retrieve_turn_context_sources"
    )

    prepare_context = next(
        node
        for node in runtime_class.body
        if isinstance(
            node,
            ast.AsyncFunctionDef,
        )
        and node.name
        == "prepare_generation_context"
    )

    def calls(
        node,
        owner,
        attr,
    ):
        return [
            child
            for child in ast.walk(node)
            if isinstance(
                child,
                ast.Call,
            )
            and isinstance(
                child.func,
                ast.Attribute,
            )
            and child.func.attr == attr
            and isinstance(
                child.func.value,
                ast.Name,
            )
            and child.func.value.id == owner
        ]

    # Major chat boundary: retrieval fan-in.
    assert (
        len(
            calls(
                chat_fn,
                "_cognitive_runtime",
                "retrieve_turn_context_sources",
            )
        )
        == 1
    )

    # chat.py no longer owns the lower-level retrieval call.
    assert (
        calls(
            chat_fn,
            "_cognitive_runtime",
            "retrieve_chat_memory_assembly",
        )
        == []
    )

    retrieval_calls = calls(
        source_fan_in,
        "self",
        "retrieve_chat_memory_assembly",
    )

    assert len(
        retrieval_calls
    ) == 1

    retrieval_call = (
        retrieval_calls[0]
    )

    retrieval_query = next(
        keyword.value
        for keyword in retrieval_call.keywords
        if keyword.arg == "query_text"
    )

    assert isinstance(
        retrieval_query,
        ast.Name,
    )

    assert (
        retrieval_query.id
        == "user_message"
    )

    # Major chat boundary: complete model-context preparation.
    assert (
        len(
            calls(
                chat_fn,
                "_cognitive_runtime",
                "prepare_generation_context",
            )
        )
        == 1
    )

    # Lower-level packing now belongs inside CognitiveRuntime.
    assert (
        calls(
            chat_fn,
            "_cognitive_runtime",
            "pack_chat_memory_context",
        )
        == []
    )

    pack_calls = calls(
        prepare_context,
        "self",
        "pack_chat_memory_context",
    )

    assert len(
        pack_calls
    ) == 1

    pack_call = pack_calls[0]

    pack_query = next(
        keyword.value
        for keyword in pack_call.keywords
        if keyword.arg == "query_text"
    )

    assert isinstance(
        pack_query,
        ast.Attribute,
    )

    assert (
        pack_query.attr
        == "message"
    )

    assert isinstance(
        pack_query.value,
        ast.Name,
    )

    assert (
        pack_query.value.id
        == "body"
    )

    # Existing service remains behind the facade.
    assert (
        calls(
            chat_fn,
            "chat_memory_assembly",
            "retrieve_chat_memory_assembly",
        )
        == []
    )

    assert (
        calls(
            chat_fn,
            "chat_memory_assembly",
            "pack_chat_memory_context",
        )
        == []
    )

    # Old inline fallback packing must remain gone.
    assert (
        "## Additional notes (unstructured)"
        not in chat_source
    )

    assert (
        "for m in legacy_memories[:5]"
        not in chat_source
    )

def test_chat_memory_assembly_preserves_retrieval_fan_in_contract() -> None:
    source = Path("app/services/chat_memory_assembly.py").read_text(encoding="utf-8")

    assert "memory_limit: int = 12" in source
    assert "summary_limit: int = 6" in source
    assert "memory.retrieve_relevant(user_id, query_text, limit=memory_limit)" in source
    assert "retrieve_related_summaries(" in source
    assert "limit=summary_limit" in source


def test_chat_memory_assembly_owns_packer_telemetry_contract() -> None:
    source = Path("app/services/chat_memory_assembly.py").read_text(encoding="utf-8")

    assert "pack_memory_context_for_prompt(" in source
    assert "query_text=query_text" in source
    assert "memory_context_packer: memories_in=%d memories_out=%d" in source
    assert "packed_chars=%d intent=%s" in source
