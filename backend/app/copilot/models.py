"""Copilot request and evidence models."""

from typing import Literal

from pydantic import BaseModel, Field


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    deal_id: str | None = Field(default=None, max_length=60)
    history: list[HistoryItem] = Field(default_factory=list, max_length=8)


class Source(BaseModel):
    """One piece of evidence shown to the model and to the user.

    `id` is the label the model uses in its answer, for example S2.
    `ref` is the real identifier in the database (a task id or a chunk id).
    """

    id: str
    type: Literal["deal", "task", "playbook"]
    ref: str
    title: str
    snippet: str
    meta: dict[str, str] = Field(default_factory=dict)
