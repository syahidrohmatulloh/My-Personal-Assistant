from pathlib import Path

SCHEMAS = [
    Path("app/schemas.py").read_text(encoding="utf-8"),
    Path("app/schemas/__init__.py").read_text(encoding="utf-8"),
]
CONVERSATIONS = Path("app/routers/conversations.py").read_text(encoding="utf-8")


def test_message_out_exposes_public_attachments():
    for schema in SCHEMAS:
        if "class MessageOut(BaseModel):" not in schema:
            continue
        assert "class AttachmentOut(BaseModel):" in schema
        message_block = schema.split("class MessageOut(BaseModel):", 1)[1].split("\n\nclass ", 1)[0]
        assert "attachments: list[AttachmentOut]" in message_block


def test_list_messages_hydrates_attachments_without_storage_path():
    assert "_hydrate_message_attachments" in CONVERSATIONS
    assert "message_attachments" in CONVERSATIONS
    assert "storage_path" not in CONVERSATIONS.split("def _public_attachment_row", 1)[1].split("def _hydrate_message_attachments", 1)[0]
    assert '"attachments": grouped.get(message.get("id"), [])' in CONVERSATIONS
