"""Login rules: check the password, limit guessing, issue a token, audit everything."""

import time
from collections import defaultdict
from collections.abc import Callable

import structlog

from app.audit.models import build_event
from app.audit.service import AuditService
from app.auth.models import LoginResponse, User, UserOut
from app.auth.repository import UserRepository
from app.core.config import Settings
from app.core.errors import RateLimitError, UnauthorizedError
from app.core.passwords import DUMMY_HASH, verify_password
from app.core.security import CurrentUser, Role
from app.core.tokens import issue_token

log = structlog.get_logger()

MAX_FAILURES = 5  # failed attempts inside the window that trigger a lock
WINDOW_SECONDS = 15 * 60  # only failures from the last 15 minutes count
LOCK_SECONDS = 5 * 60  # how long the username stays locked


class LoginGuard:
    """Counts failed logins per username and locks the account for a few minutes.

    Limit: kept in the memory of one API process. With several API instances you would keep the
    counters in a shared store such as Redis. It is also per username, not per address.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock  # injectable so tests can move time without waiting
        self._failures: dict[str, list[float]] = defaultdict(list)  # username -> failure times
        self._locked_until: dict[str, float] = {}  # username -> time the lock ends

    def _now(self) -> float:
        """Current time in seconds (from the injected clock)."""
        return self._clock()

    def check(self, username: str) -> None:
        """Call before verifying a password: raises RateLimitError (429) while locked."""
        until = self._locked_until.get(username, 0.0)
        remaining = until - self._now()
        if remaining > 0:
            minutes = max(1, int(remaining // 60) + 1)  # round up so it never says 0 minutes
            raise RateLimitError(
                f"Too many failed sign-in attempts. Try again in about {minutes} minute(s)."
            )

    def failed(self, username: str) -> None:
        """Record a wrong password; lock the username once MAX_FAILURES is reached."""
        now = self._now()
        # Keep only failures inside the window, then add this one.
        recent = [t for t in self._failures[username] if now - t < WINDOW_SECONDS]
        recent.append(now)
        self._failures[username] = recent
        if len(recent) >= MAX_FAILURES:
            self._locked_until[username] = now + LOCK_SECONDS
            self._failures[username] = []  # start counting again after the lock ends

    def succeeded(self, username: str) -> None:
        """A correct login clears the failure count and any lock."""
        self._failures.pop(username, None)
        self._locked_until.pop(username, None)


# One guard per process, shared by all requests.
GUARD = LoginGuard()


class AuthService:
    """Sign-in use cases. Talks to storage, the audit trail and the lockout guard."""

    def __init__(
        self,
        users: UserRepository,
        audit: AuditService,
        settings: Settings,
        guard: LoginGuard = GUARD,
    ) -> None:
        self._users = users
        self._audit = audit
        self._settings = settings
        self._guard = guard

    async def login(self, username: str, password: str) -> LoginResponse:
        """Check credentials and return a token. Every outcome is audited."""
        # 1) Refuse early if the username is locked. 2) Look the user up.
        self._guard.check(username)
        user = await self._users.get(username)
        # Always verify against a hash, even for an unknown user, so timing does not reveal it.
        ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
        # Unknown user, disabled user and wrong password all give the same message on purpose.
        if user is None or not user.active or not ok:
            self._guard.failed(username)
            await self._record(username, Role.viewer, "auth.login_failed")
            raise UnauthorizedError("Wrong username or password.")
        self._guard.succeeded(username)
        await self._record(user.username, user.role, "auth.login")
        # Success: issue a token that lives jwt_ttl_minutes and tell the client in seconds.
        ttl = self._settings.jwt_ttl_minutes
        token = issue_token(
            username=user.username,
            role=user.role.value,
            display_name=user.display_name,
            secret=self._settings.jwt_secret,
            ttl_minutes=ttl,
        )
        return LoginResponse(access_token=token, expires_in=ttl * 60, user=_out(user))

    async def logout(self, user: CurrentUser) -> None:
        """Only writes the audit entry; the token itself expires on its own (documented limit)."""
        await self._record(user.name, user.role, "auth.logout")

    async def me(self, user: CurrentUser) -> UserOut:
        """Who is signed in, preferring the stored record over what the token claims."""
        stored = await self._users.get(user.name)
        if stored is not None and stored.active:
            return _out(stored)
        # Demo mode, or a user removed after the token was issued: report what the token says.
        return UserOut(
            username=user.name, display_name=user.display_name or user.name, role=user.role
        )

    async def list_users(self) -> list[UserOut]:
        """All users without password hashes (admin only at the router)."""
        return [_out(u) for u in await self._users.all_users()]

    async def _record(self, username: str, role: Role, action: str) -> None:
        """Write one audit event for a sign-in action; a failed write is logged, not raised."""
        event = build_event(
            CurrentUser(name=username[:60], role=role), action, "user", username[:60]
        )
        try:
            await self._audit.record(event)
        except Exception as exc:  # noqa: BLE001 - auditing must not break sign-in
            log.error("audit_write_failed", error=type(exc).__name__, detail=str(exc)[:200])


def _out(user: User) -> UserOut:
    """Convert the stored User into the public shape (drops the password hash)."""
    return UserOut(
        username=user.username, display_name=user.display_name, role=user.role, active=user.active
    )
