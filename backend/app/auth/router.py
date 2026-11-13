"""Sign in, who am I, sign out."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.auth.models import DemoAccount, LoginRequest, LoginResponse, UserOut
from app.auth.service import AuthService
from app.core.config import Settings, get_settings
from app.core.security import CurrentUser, Role, get_current_user, require_roles
from app.deps import get_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

Service = Annotated[AuthService, Depends(get_auth_service)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, service: Service, response: Response) -> LoginResponse:
    """Exchange username and password for a token."""
    # no-store: browsers and proxies must never cache a response that contains a token.
    response.headers["Cache-Control"] = "no-store"
    return await service.login(body.username, body.password)


@router.get("/me", response_model=UserOut)
async def me(user: User, service: Service) -> UserOut:
    """The signed-in user; the frontend calls this to learn who it is."""
    return await service.me(user)


@router.post("/logout", status_code=204)
async def logout(user: User, service: Service) -> None:
    """Record the sign-out in the audit trail (returns 204, no body)."""
    await service.logout(user)


@router.get("/users", response_model=list[UserOut])
async def users(
    _admin: Annotated[CurrentUser, Depends(require_roles(Role.admin))], service: Service
) -> list[UserOut]:
    """List all users. The dependency above makes this admin only (others get 403)."""
    return await service.list_users()


@router.get("/demo-accounts", response_model=list[DemoAccount])
async def demo_accounts(
    settings: Annotated[Settings, Depends(get_settings)], service: Service
) -> list[DemoAccount]:
    """Usernames and roles of the seeded demo users, so the login page can offer them.

    Development only: it returns nothing in production. It never returns passwords.
    """
    # Outside development this list stays empty so production never advertises accounts.
    if settings.app_env != "development":
        return []
    return [
        DemoAccount(username=u.username, display_name=u.display_name, role=u.role)
        for u in await service.list_users()
    ]
