from pathlib import Path

CHAT = Path("app/routers/chat.py").read_text(encoding="utf-8")


def _stream_block() -> str:
    start = CHAT.index("async def _stream_claude_response(")
    candidates = [
        idx for idx in (
            CHAT.find("\nasync def ", start + 1),
            CHAT.find("\ndef ", start + 1),
            CHAT.find("\n@router.", start + 1),
        )
        if idx != -1
    ]
    end = min(candidates) if candidates else len(CHAT)
    return CHAT[start:end]


def _stream_call_block() -> str:
    start = CHAT.index("_stream_claude_response(\n")
    end = CHAT.index("        ),", start) + len("        ),")
    return CHAT[start:end]


def test_stream_signature_accepts_client_context():
    assert "async def _stream_claude_response(" in CHAT
    assert "client_context: dict | None = None," in _stream_block()


def test_call_site_passes_body_client_context():
    assert "client_context=body.client_context," in _stream_call_block()


def test_stream_body_does_not_reference_body_client_context():
    stream = _stream_block()
    assert "body.client_context" not in stream
    assert "client_context=client_context," in stream
