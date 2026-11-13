"""Who is calling, and may they do this?

Two modes, chosen with AUTH_MODE:
- "jwt" (default): the caller sends `Authorization: Bearer <token>` obtained from POST /auth/login.
  The token is signed, so the role inside it cannot be changed by the caller.
- "demo": the caller names themselves in X-Demo-Role / X-Demo-User headers. That is NOT
  authentication; it exists for tests and quick experiments and is refused in production.

Every endpoint depends on `get_current_user` (directly or through `require_roles`), so
replacing it with an OIDC validator later touches nothing else.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import BadRequestError, ForbiddenError, UnauthorizedError
from app.core.tokens import decode_token


class Role(StrEnum):
    """The five roles of the portal. The string value is what is stored in the token."""

    viewer = "viewer"
    marketer = "marketer"
    syndicate = "syndicate"
    approver = "approver"
    admin = "admin"


@dataclass(frozen=True)
class CurrentUser:
    """The caller as the rest of the code sees them (frozen, so it cannot be changed mid-request)."""

    name: str
    role: Role
    display_name: str = ""


# Used in demo mode only: removes anything but letters, digits, space, dot, @ and dash from a name.
_CONTROL_CHARS = re.compile(r"[^\w .@-]")


def _bearer(authorization: str | None) -> str | None:
    """Pull the token out of an 'Authorization: Bearer <token>' header, or None if absent."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_demo_role: Annotated[str | None, Header()] = None,
    x_demo_user: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """FastAPI dependency: work out who is calling. Raises 401 when they are not signed in."""
    if settings.auth_mode == "jwt":
        token = _bearer(authorization)
        if token is None:
            raise UnauthorizedError("Please sign in.")
        claims = decode_token(token, settings.jwt_secret)
        # The role comes from the signed token. A role value we do not know means a bad token.
        try:
            role = Role(claims["role"])
        except ValueError as exc:
            raise UnauthorizedError("Your session is not valid. Please sign in again.") from exc
        return CurrentUser(name=claims["sub"], role=role, display_name=claims.get("name", ""))

    # Demo mode (development and tests only): trust the headers; default to the least power.
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
        # Admin passes everywhere; everyone else needs one of the listed roles, else 403.
        if user.role is Role.admin or user.role in allowed:
            return user
        needed = ", ".join(r.value for r in allowed)
        raise ForbiddenError(f"The role '{user.role.value}' may not do this. Needed: {needed}.")

    return dependency
