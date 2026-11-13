"""Users and login payloads."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.security import Role

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")


class User(BaseModel):
    """A user as stored. Internal only: it carries the password hash."""

    username: str
    display_name: str
    role: Role
    active: bool = True
    password_hash: str = Field(repr=False)  # repr=False keeps the hash out of logs and tracebacks


class UserOut(BaseModel):
    """What the API shows about a user. Never includes the password hash."""

    username: str
    display_name: str
    role: Role
    active: bool = True


class LoginRequest(BaseModel):
    """Body of POST /auth/login. Length limits stop absurdly large inputs."""

    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("username")
    @classmethod
    def lowercase(cls, value: str) -> str:
        # Usernames are not case sensitive: 'Anna.Syndicate ' and 'anna.syndicate' are the same.
        return value.strip().lower()


class LoginResponse(BaseModel):
    """What a successful login returns: the token, its lifetime in seconds, and the user."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


class DemoAccount(BaseModel):
    """A demo account shown on the login page (never includes a password)."""

    username: str
    display_name: str
    role: Role


# The users the seed creates (development). The password comes from DEMO_USER_PASSWORD.
DEMO_USERS: tuple[tuple[str, str, Role], ...] = (
    ("admin.user", "Alex Admin", Role.admin),
    ("anna.syndicate", "Anna Keller (Syndicate)", Role.syndicate),
    ("marco.approver", "Marco Rossi (Approver)", Role.approver),
    ("mia.marketer", "Mia Berg (Marketer)", Role.marketer),
    ("vera.viewer", "Vera Lang (Viewer)", Role.viewer),
)
DEFAULT_DEMO_PASSWORD = "DealCopilot-Demo-1"
