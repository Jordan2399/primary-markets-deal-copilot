"""Admin console shapes: who has access and what they have been doing."""

from pydantic import BaseModel

from app.core.security import Role


class UserActivity(BaseModel):
    username: str
    display_name: str
    role: Role
    active: bool
    actions: int  # audit events written by this user (last 500 events)
    last_action: str | None  # ISO timestamp of the latest event, or None


class RoleSummary(BaseModel):
    role: Role
    users: int


class AdminOverview(BaseModel):
    users: list[UserActivity]
    roles: list[RoleSummary]
    events_total: int  # events looked at (the most recent 500)
    ai_calls: int  # events that carry a model name: answers written by the language model
    sign_ins: int
    failed_sign_ins: int
