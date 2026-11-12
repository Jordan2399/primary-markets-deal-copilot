"""Demo identity and role checks.

DEMO ONLY: the caller says who they are in two headers. This is not authentication.
In a real deployment, replace `get_current_user` with a dependency that validates an OIDC
token and maps its claims to a `CurrentUser`. Every endpoint already depends on this one
function, so that replacement touches nothing else.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header

from app.core.errors import BadRequestError, ForbiddenError


class Role(StrEnum):
    viewer = "viewer"
    marketer = "marketer"
    syndicate = "syndicate"
    approver = "approver"
    admin = "admin"


@dataclass(frozen=True)
class CurrentUser:
    name: str
    role: Role


_CONTROL_CHARS = re.compile(r"[^\w .@-]")


def get_current_user(
    x_demo_role: Annotated[str | None, Header()] = None,
    x_demo_user: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    role = Role.viewer
    if x_demo_role:
        try:
            role = Role(x_demo_role.strip().lower())
        except ValueError as exc:
            allowed = ", ".join(r.value for r in Role)
            raise BadRequestError(
                f"Unknown role '{x_demo_role[:30]}'. Use one of: {allowed}."
            ) from exc
    name = _CONTROL_CHARS.sub("", (x_demo_user or "demo.user"))[:60] or "demo.user"
    return CurrentUser(name=name, role=role)


def require_roles(*allowed: Role):  # type: ignore[no-untyped-def]
    """Build a dependency that only lets the given roles through (admin always passes)."""

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role is Role.admin or user.role in allowed:
            return user
        needed = ", ".join(r.value for r in allowed)
        raise ForbiddenError(f"The role '{user.role.value}' may not do this. Needed: {needed}.")

    return dependency
