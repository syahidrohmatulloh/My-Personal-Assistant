"""CRUD endpoints for conversations and their messages.

All endpoints depend on `get_current_user_id`, which verifies the JWT and
gives us the user's UUID. Every query then filters by that UUID — so even if
RLS were disabled, a user could never see another user's data through these
routes.
"""

import asyncio
import logging

from fastapi import Query, APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.schemas import ConversationOut, CreateConversationIn, MessageOut
from app.services import companion
from app.services.claude import get_claude
from app.services.supabase_client import get_supabase, safe_execute

log = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["conversations"])


def _clean_assistant_name(value: object) -> str:
    name = str(value or "").strip()
    return name or "Assistant"


def _main_chat_title_from_settings(settings_row: dict | None) -> str:
    assistant_name = _clean_assistant_name((settings_row or {}).get("assistant_name"))
    return f"Main Chat - {assistant_name}"



class RenameConversationIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)



async def _is_protected_conversation(user_id: str, conversation_id: str) -> bool:
    main_chat = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("user_main_chats")
            .select("conversation_id")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .maybe_single()
            .execute()
        )
    )
    if main_chat and main_chat.data:
        return True

    briefing_chat = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("user_briefing_chats")
            .select("conversation_id")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .maybe_single()
            .execute()
        )
    )
    if briefing_chat and briefing_chat.data:
        return True

    linked_briefing = await asyncio.to_thread(
        lambda: safe_execute(
            lambda sb: sb.table("daily_briefings")
            .select("id")
            .eq("user_id", user_id)
            .eq("conversation_id", conversation_id)
            .limit(1)
            .maybe_single()
            .execute()
        )
    )
    return bool(linked_briefing and linked_briefing.data)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user_id: str = Depends(get_current_user_id)):
    """Return all conversations for the current user, newest first."""
    supabase = get_supabase()
    result = (
        supabase.table("conversations")
        .select("id, title, created_at, updated_at, style_profile_id")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/main", response_model=ConversationOut)
async def get_or_create_main_conversation(
    user_id: str = Depends(get_current_user_id),
):
    """Return the user's designated Main Chat.

    If the mapping does not exist yet, create a stable Main Chat conversation
    and store it in user_main_chats. The title follows the current assistant
    display name, falling back to Assistant when no name is set.
    """
    supabase = get_supabase()
    companion_settings = await companion.get_settings(user_id)
    main_chat_title = _main_chat_title_from_settings(companion_settings)

    mapping = (
        supabase.table("user_main_chats")
        .select("conversation_id")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    conversation_id = (mapping.data or {}).get("conversation_id") if mapping else None

    if conversation_id:
        existing = (
            supabase.table("conversations")
            .select("id, title, created_at, updated_at, style_profile_id")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if existing and existing.data:
            main_chat = existing.data

            if main_chat.get("title") != main_chat_title:
                updated = (
                    supabase.table("conversations")
                    .update({"title": main_chat_title})
                    .eq("id", conversation_id)
                    .eq("user_id", user_id)
                    .execute()
                )
                if updated.data:
                    return updated.data[0]

            return main_chat

    created = (
        supabase.table("conversations")
        .insert(
            {
                "user_id": user_id,
                "title": main_chat_title,
            }
        )
        .execute()
    )

    if not created.data:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to create Main Chat",
        )

    main_chat = created.data[0]

    supabase.table("user_main_chats").upsert(
        {
            "user_id": user_id,
            "conversation_id": main_chat["id"],
        }
    ).execute()

    return main_chat


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationIn,
    user_id: str = Depends(get_current_user_id),
):
    """Start a new empty conversation."""
    supabase = get_supabase()
    row = {"user_id": user_id, "title": body.title}
    if body.style_profile_id:
        # Verify the profile belongs to this user before linking.
        prof = (
            supabase.table("style_profiles")
            .select("id")
            .eq("id", body.style_profile_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if prof and prof.data:
            row["style_profile_id"] = body.style_profile_id
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Style profile not found"
            )
    result = supabase.table("conversations").insert(row).execute()
    if not result.data:
        raise HTTPException(500, "Failed to create conversation")
    return result.data[0]


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(
    conversation_id: str,
    body: RenameConversationIn,
    user_id: str = Depends(get_current_user_id),
):
    """Manually rename a conversation. User-edited titles are durable —
    auto-rename background jobs respect them and don't overwrite."""
    supabase = get_supabase()
    result = (
        supabase.table("conversations")
        .update({"title": body.title.strip()})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return result.data[0]


class SetStyleIn(BaseModel):
    """Body for setting / clearing a conversation's style profile.

    `style_profile_id = None` means "use Default style" — that's the rollback
    operation. Per the design contract, Default = exactly the assistant's
    behavior before this feature shipped.
    """

    style_profile_id: str | None = None


@router.patch("/{conversation_id}/style", response_model=ConversationOut)
async def set_conversation_style(
    conversation_id: str,
    body: SetStyleIn,
    user_id: str = Depends(get_current_user_id),
):
    """Set or clear the style profile for a single conversation.

    Rollback to Default: send {"style_profile_id": null}. Takes effect on the
    user's NEXT message in this conversation. Existing messages are not
    rewritten — style applies forward, not retroactively.

    If the profile_id doesn't belong to the user or doesn't exist, we return
    400. We do NOT silently fall back, because that would hide bugs in the
    frontend.
    """
    supabase = get_supabase()

    # Verify conversation ownership first.
    convo = (
        supabase.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not convo or not convo.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    # If setting a profile (not clearing), verify it belongs to the user.
    if body.style_profile_id is not None:
        prof = (
            supabase.table("style_profiles")
            .select("id")
            .eq("id", body.style_profile_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not prof or not prof.data:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Style profile not found"
            )

    result = (
        supabase.table("conversations")
        .update({"style_profile_id": body.style_profile_id})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update style"
        )

    log.info(
        "conversation style set: user=%s convo=%s style=%s",
        user_id[:8],
        conversation_id[:8],
        body.style_profile_id or "default",
    )
    return result.data[0]


@router.post("/{conversation_id}/regenerate-title", response_model=ConversationOut)
async def regenerate_title(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """Re-run title generation for a conversation. Useful for backfilling
    'New chat' / 'Untitled' titles on old conversations.

    Synchronous Haiku call so the user sees the new title immediately when
    the UI refetches. Not in background — user explicitly asked for it.
    """
    supabase = get_supabase()

    # Verify ownership.
    convo = (
        supabase.table("conversations")
        .select("id, title")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not convo or not convo.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    # Load first ~10 messages — plenty for a title.
    msgs_res = (
        supabase.table("messages")
        .select("role, content")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .limit(10)
        .execute()
    )
    messages = msgs_res.data or []
    if len(messages) < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Conversation needs at least one exchange before title can be generated",
        )

    new_title = await _haiku_title(messages)
    if not new_title:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Title generation failed — try again",
        )

    updated = (
        supabase.table("conversations")
        .update({"title": new_title})
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    return updated.data[0]


async def _haiku_title(messages: list[dict]) -> str | None:
    """Call Haiku to generate a 3-6 word title. Returns None on failure."""
    claude = get_claude()

    # Compose enough context for the model. Cap each message; titles need
    # gist, not full transcripts.
    excerpt_parts: list[str] = []
    for m in messages[:6]:
        excerpt_parts.append(f"{m['role'].upper()}: {m['content'][:300]}")
    excerpt = "\n\n".join(excerpt_parts)

    try:
        response = await claude.messages.create(
            model="claude-haiku-4-5",
            max_tokens=30,
            system=(
                "Generate a concise 3-6 word title summarizing this conversation. "
                "Use the same language as the conversation. "
                "Output ONLY the title — no quotes, no punctuation at end, no commentary."
            ),
            messages=[{"role": "user", "content": excerpt}],
        )
    except Exception as exc:
        log.warning("regenerate-title: Haiku failed: %s", exc)
        return None

    block = next((b for b in response.content if b.type == "text"), None)
    if not block:
        return None
    title = block.text.strip().strip('"').strip("'")[:60]
    return title or None


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a conversation and cascade its messages.

    We filter by both id AND user_id so a user can never delete someone else's
    conversation, even if they guess the ID.
    """
    supabase = get_supabase()
    supabase.table("conversations").delete().eq("id", conversation_id).eq(
        "user_id", user_id
    ).execute()


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    limit: int = Query(default=80, ge=1, le=200),
    before: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """Load a page of messages, oldest first within the returned page.

    By default this returns the latest 80 messages. Pass before=<created_at>
    to load messages older than the earliest message currently rendered.
    """
    supabase = get_supabase()

    # First, prove the conversation belongs to this user. Without this check,
    # someone could fetch any conversation's messages by guessing its UUID.
    convo = (
        supabase.table("conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not convo or not convo.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    query = (
        supabase.table("messages")
        .select("id, role, content, created_at")
        .eq("conversation_id", conversation_id)
    )

    if before:
        query = query.lt("created_at", before)

    result = query.order("created_at", desc=True).limit(limit).execute()
    return list(reversed(result.data or []))
