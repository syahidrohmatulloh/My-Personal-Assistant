"""CRUD endpoints for conversations and their messages.

All endpoints depend on `get_current_user_id`, which verifies the JWT and
gives us the user's UUID. Every query then filters by that UUID — so even if
RLS were disabled, a user could never see another user's data through these
routes.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user_id
from app.schemas import ConversationOut, CreateConversationIn, MessageOut
from app.services.supabase_client import get_supabase

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user_id: str = Depends(get_current_user_id)):
    """Return all conversations for the current user, newest first."""
    supabase = get_supabase()
    result = (
        supabase.table("conversations")
        .select("id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: CreateConversationIn,
    user_id: str = Depends(get_current_user_id),
):
    """Start a new empty conversation."""
    supabase = get_supabase()
    result = (
        supabase.table("conversations")
        .insert({"user_id": user_id, "title": body.title})
        .execute()
    )
    if not result.data:
        raise HTTPException(500, "Failed to create conversation")
    return result.data[0]


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
    user_id: str = Depends(get_current_user_id),
):
    """Load all messages in a conversation, oldest first."""
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

    result = (
        supabase.table("messages")
        .select("id, role, content, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )
    return result.data
