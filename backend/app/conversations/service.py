"""Conversation rules: ownership, history for follow-ups, saving a question and its answer."""

import uuid

from app.audit.models import build_event
from app.audit.service import AuditService
from app.conversations.models import (
    ID_PATTERN,
    ConversationDetail,
    ConversationSummary,
    StoredMessage,
    make_title,
)
from app.conversations.repository import ConversationRepository
from app.copilot.models import HistoryItem, Source
from app.core.errors import NotFoundError
from app.core.security import CurrentUser

HISTORY_MESSAGES = 6  # how much of the thread the Copilot sees when it answers a follow-up
LIST_LIMIT = 100
NOT_FOUND = "That conversation does not exist."


class ConversationService:
    """Thread use cases. The user is always passed in, and every read is scoped to them."""

    def __init__(self, repo: ConversationRepository, audit: AuditService) -> None:
        self._repo = repo
        self._audit = audit

    async def list_mine(self, user: CurrentUser) -> list[ConversationSummary]:
        """The user's threads, most recently active first."""
        return await self._repo.list_owned(user.name, LIST_LIMIT)

    async def get(self, user: CurrentUser, conversation_id: str) -> ConversationDetail:
        """Return one thread or raise 404. Also the ownership check used by the other methods."""
        found = None
        # A malformed id never reaches the database.
        if ID_PATTERN.match(conversation_id):
            found = await self._repo.get(conversation_id, user.name)
        if found is None:
            # Same answer for "missing" and "someone else's": the API does not reveal which.
            raise NotFoundError(NOT_FOUND)
        return found

    async def rename(
        self, user: CurrentUser, conversation_id: str, title: str
    ) -> ConversationDetail:
        """Change a thread title (whitespace is tidied, empty becomes a default)."""
        await self.get(user, conversation_id)  # 404 when missing or not theirs
        clean = " ".join(title.split())
        if not clean:
            clean = "New conversation"
        await self._repo.rename(conversation_id, user.name, clean)
        return await self.get(user, conversation_id)

    async def delete(self, user: CurrentUser, conversation_id: str) -> None:
        """Delete a thread and its messages; the audit entry is written in the same transaction."""
        await self.get(user, conversation_id)
        event = build_event(
            user, "conversation.delete", "conversation", conversation_id, details={}
        )
        if not await self._repo.delete(conversation_id, user.name, event):
            raise NotFoundError(NOT_FOUND)

    async def context_for(
        self, user: CurrentUser, conversation_id: str | None
    ) -> tuple[str, list[HistoryItem], bool]:
        """Return (conversation id, recent history, is_new) for the next question.

        A new id is created on the server; the client never chooses the id of a new thread.
        """
        if conversation_id is None:
            return uuid.uuid4().hex, [], True
        await self.get(user, conversation_id)  # ownership check
        # Only the last few messages are used, and each is capped, to keep the prompt small.
        recent = await self._repo.recent_messages(conversation_id, user.name, HISTORY_MESSAGES)
        return (
            conversation_id,
            [HistoryItem(role=m.role, content=m.content[:4000]) for m in recent],
            False,
        )

    async def save_turn(
        self,
        user: CurrentUser,
        conversation_id: str,
        deal_id: str | None,
        question: str,
        answer: str,
        *,
        sources: list[Source],
        cited: list[str],
        intent: str,
        audit_id: str | None,
    ) -> None:
        """Store the question and its answer (with evidence) as one unit, after success only."""
        messages = [
            StoredMessage(id=uuid.uuid4().hex, role="user", content=question),
            StoredMessage(
                id=uuid.uuid4().hex,
                role="assistant",
                content=answer,
                sources=sources,
                cited=cited,
                intent=intent,
                audit_id=audit_id,
            ),
        ]
        # The title comes from the first question; the repository keeps it if the thread exists.
        await self._repo.append_turn(
            conversation_id, user.name, deal_id, make_title(question), messages
        )
