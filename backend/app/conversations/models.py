"""Saved Copilot conversations (threads)."""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.copilot.models import Source

# A valid conversation id is exactly 32 lowercase hex characters (what the server generates).
ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
TITLE_MAX = 60  # longest thread title, in characters


class StoredMessage(BaseModel):
    """One saved message. Assistant messages also keep their evidence, so reloading shows it."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: str = ""
    sources: list[Source] = Field(default_factory=list)
    cited: list[str] = Field(default_factory=list)
    intent: str | None = None
    audit_id: str | None = None


class ConversationSummary(BaseModel):
    """A thread as shown in the sidebar list (no messages)."""

    id: str
    title: str
    deal_id: str | None = None
    created_at: str
    updated_at: str
    message_count: int = 0


class ConversationDetail(ConversationSummary):
    """A thread with all its messages, oldest first."""

    messages: list[StoredMessage] = Field(default_factory=list)


class RenameRequest(BaseModel):
    """Body of the rename call; empty titles are rejected by min_length."""

    title: str = Field(min_length=1, max_length=TITLE_MAX)


def make_title(question: str) -> str:
    """A short title from the first question: whitespace collapsed, cut at 60 characters."""
    text = " ".join(question.split())  # split() with no argument collapses all whitespace
    if len(text) <= TITLE_MAX:
        return text or "New conversation"
    return text[: TITLE_MAX - 1].rstrip() + "…"
