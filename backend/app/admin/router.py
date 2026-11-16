"""Admin console endpoint. Administrators only; everyone else gets 403."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.admin.models import AdminOverview, RoleSummary, UserActivity
from app.audit.service import AuditService
from app.auth.service import AuthService
from app.core.security import CurrentUser, Role, require_roles
from app.deps import get_audit_service, get_auth_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverview)
async def overview(
    _admin: Annotated[CurrentUser, Depends(require_roles(Role.admin))],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
) -> AdminOverview:
    users = await auth.list_users()
    events = await audit.list_events(limit=500)
    by_actor: dict[str, list[str]] = {}
    for e in events:
        by_actor.setdefault(e.actor, []).append(e.ts)

    rows = []
    for u in users:
        # Events store the display name (build_event uses user.name), so match on both.
        stamps = by_actor.get(u.username, []) + by_actor.get(u.display_name, [])
        rows.append(
            UserActivity(
                username=u.username,
                display_name=u.display_name,
                role=u.role,
                active=u.active,
                actions=len(stamps),
                last_action=max(stamps) if stamps else None,
            )
        )
    roles = [RoleSummary(role=r, users=sum(1 for u in users if u.role == r)) for r in Role]
    return AdminOverview(
        users=rows,
        roles=roles,
        events_total=len(events),
        ai_calls=sum(1 for e in events if e.model),
        sign_ins=sum(1 for e in events if e.action == "auth.login"),
        failed_sign_ins=sum(1 for e in events if e.action == "auth.login_failed"),
    )
