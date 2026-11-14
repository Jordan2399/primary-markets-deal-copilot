"""Saved conversations. Every user sees only their own."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.conversations.models import ConversationDetail, ConversationSummary, RenameRequest
from app.conversations.service import ConversationService
from app.core.security import CurrentUser, get_current_user
from app.deps import get_conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])

Service = Annotated[ConversationService, Depends(get_conversation_service)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(user: User, service: Service) -> list[ConversationSummary]:
    """The caller's threads for the sidebar."""
    return await service.list_mine(user)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str, user: User, service: Service
) -> ConversationDetail:
    """One thread with messages; 404 for a missing or foreign id."""
    return await service.get(user, conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationDetail)
async def rename_conversation(
    conversation_id: str, body: RenameRequest, user: User, service: Service
) -> ConversationDetail:
    """Rename a thread."""
    return await service.rename(user, conversation_id, body.title)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, user: User, service: Service) -> None:
    """Delete a thread (204, no body)."""
    await service.delete(user, conversation_id)
