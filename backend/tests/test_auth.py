"""Login, tokens, roles and the production safety check."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.models import User
from app.auth.service import MAX_FAILURES, LoginGuard
from app.core.config import Settings, get_settings
from app.core.errors import RateLimitError, UnauthorizedError
from app.core.passwords import hash_password, verify_password
from app.core.security import Role
from app.core.tokens import ALGORITHM, decode_token, issue_token
from app.llm.fake import FakeLLM
from tests.conftest import JWT_SECRET, Env, build_env
from tests.fakes import add_deal

PASSWORD = "Correct-Horse-1"


def jwt_env() -> Env:
    env = build_env(FakeLLM(), auth_mode="jwt")
    for name, role in [
        ("sam.syndicate", Role.syndicate),
        ("vera.viewer", Role.viewer),
        ("marco.approver", Role.approver),
        ("admin.user", Role.admin),
    ]:
        env.users.users[name] = User(
            username=name,
            display_name=name.title(),
            role=role,
            password_hash=hash_password(PASSWORD),
        )
    return env


def login(env: Env, username: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return env.client.post("/api/v1/auth/login", json={"username": username, "password": password})


def bearer(env: Env, username: str) -> dict[str, str]:
    token = login(env, username).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---- passwords


def test_password_roundtrip_and_salt() -> None:
    a, b = hash_password(PASSWORD), hash_password(PASSWORD)
    assert a != b  # random salt
    assert verify_password(PASSWORD, a)
    assert not verify_password("wrong", a)
    assert PASSWORD not in a


@pytest.mark.parametrize("stored", ["", "plain", "scrypt$x$y", "md5$1$2$3$4$5", "scrypt$a$b$c$d$e"])
def test_malformed_hash_is_a_failure_not_a_crash(stored: str) -> None:
    assert verify_password(PASSWORD, stored) is False


# ---- tokens


def test_token_roundtrip() -> None:
    token = issue_token(
        username="sam", role="syndicate", display_name="Sam", secret=JWT_SECRET, ttl_minutes=5
    )
    claims = decode_token(token, JWT_SECRET)
    assert claims["sub"] == "sam" and claims["role"] == "syndicate"


def test_expired_token_is_rejected() -> None:
    token = issue_token(
        username="sam", role="syndicate", display_name="", secret=JWT_SECRET, ttl_minutes=-1
    )
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_token(token, JWT_SECRET)


def test_token_signed_with_another_secret_is_rejected() -> None:
    token = issue_token(
        username="sam", role="admin", display_name="", secret="x" * 40, ttl_minutes=5
    )
    with pytest.raises(UnauthorizedError):
        decode_token(token, JWT_SECRET)


def test_token_without_a_signature_is_rejected() -> None:
    claims = {
        "iss": "deal-copilot",
        "sub": "sam",
        "role": "admin",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    forged = jwt.encode(claims, key=None, algorithm="none")  # type: ignore[arg-type]
    with pytest.raises(UnauthorizedError):
        decode_token(forged, JWT_SECRET)
    assert ALGORITHM == "HS256"


# ---- login endpoint


def test_login_returns_a_token_and_the_user() -> None:
    env = jwt_env()
    response = login(env, "sam.syndicate")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] > 0
    assert body["user"] == {
        "username": "sam.syndicate",
        "display_name": "Sam.Syndicate",
        "role": "syndicate",
        "active": True,
    }
    assert "password" not in response.text and "scrypt" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_username_is_case_insensitive() -> None:
    assert login(jwt_env(), "  SAM.Syndicate ").status_code == 200


def test_wrong_password_and_unknown_user_look_the_same() -> None:
    env = jwt_env()
    wrong = login(env, "sam.syndicate", "nope")
    unknown = login(env, "nobody.here")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert wrong.json()["error"]["code"] == "unauthorized"


def test_disabled_user_cannot_sign_in() -> None:
    env = jwt_env()
    env.users.users["vera.viewer"] = env.users.users["vera.viewer"].model_copy(
        update={"active": False}
    )
    assert login(env, "vera.viewer").status_code == 401


def test_login_and_failure_are_audited() -> None:
    env = jwt_env()
    login(env, "sam.syndicate")
    login(env, "sam.syndicate", "bad")
    actions = [e.action for e in env.repo.events]
    assert "auth.login" in actions and "auth.login_failed" in actions
    assert PASSWORD not in str([e.model_dump() for e in env.repo.events])


def test_repeated_failures_lock_the_account() -> None:
    env = jwt_env()
    for _ in range(MAX_FAILURES):
        assert login(env, "sam.syndicate", "bad").status_code == 401
    locked = login(env, "sam.syndicate", PASSWORD)  # even the right password is refused now
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "rate_limited"


def test_login_guard_unlocks_after_the_lock_time() -> None:
    now = [1000.0]
    guard = LoginGuard(clock=lambda: now[0])
    for _ in range(MAX_FAILURES):
        guard.failed("u")
    with pytest.raises(RateLimitError):
        guard.check("u")
    now[0] += 6 * 60
    guard.check("u")  # no error


def test_success_resets_the_failure_count() -> None:
    guard = LoginGuard()
    for _ in range(MAX_FAILURES - 1):
        guard.failed("u")
    guard.succeeded("u")
    guard.failed("u")
    guard.check("u")  # still not locked


# ---- who may do what


def test_endpoints_need_a_token_in_jwt_mode() -> None:
    env = jwt_env()
    for method, path in [
        ("get", "/api/v1/deals"),
        ("get", "/api/v1/stages"),
        ("get", "/api/v1/audit"),
    ]:
        response = getattr(env.client, method)(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthorized"


def test_health_stays_public() -> None:
    env = jwt_env()
    assert env.client.get("/api/v1/health/live").status_code == 200


def test_demo_headers_are_ignored_in_jwt_mode() -> None:
    env = jwt_env()
    response = env.client.get(
        "/api/v1/audit", headers={"X-Demo-Role": "admin", "X-Demo-User": "mallory"}
    )
    assert response.status_code == 401


async def test_role_comes_from_the_token() -> None:
    env = jwt_env()
    await add_deal(env.repo)
    viewer = bearer(env, "vera.viewer")
    assert env.client.get("/api/v1/deals", headers=viewer).status_code == 200
    assert env.client.get("/api/v1/audit", headers=viewer).status_code == 403
    assert env.client.get("/api/v1/audit", headers=bearer(env, "admin.user")).status_code == 200
    # a viewer cannot reach the order book; a syndicate user can reach the endpoint
    assert env.client.get("/api/v1/deals/D-DEMO-001/orderbook", headers=viewer).status_code == 403


def test_tampered_token_is_rejected() -> None:
    env = jwt_env()
    token = login(env, "vera.viewer").json()["access_token"]
    header, payload, signature = token.split(".")
    other = issue_token(
        username="vera.viewer", role="admin", display_name="", secret="y" * 40, ttl_minutes=5
    ).split(".")[1]
    response = env.client.get(
        "/api/v1/audit", headers={"Authorization": f"Bearer {header}.{other}.{signature}"}
    )
    assert response.status_code == 401


def test_me_and_logout() -> None:
    env = jwt_env()
    headers = bearer(env, "marco.approver")
    me = env.client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["role"] == "approver"
    assert env.client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert "auth.logout" in [e.action for e in env.repo.events]
    assert env.client.get("/api/v1/auth/me").status_code == 401


def test_only_admin_lists_users() -> None:
    env = jwt_env()
    assert (
        env.client.get("/api/v1/auth/users", headers=bearer(env, "sam.syndicate")).status_code
        == 403
    )
    listing = env.client.get("/api/v1/auth/users", headers=bearer(env, "admin.user"))
    assert listing.status_code == 200
    assert "password_hash" not in listing.text


def test_demo_accounts_list_names_only_and_are_empty_in_production() -> None:
    env = jwt_env()
    dev = env.client.get("/api/v1/auth/demo-accounts").json()
    assert dev and {"username", "display_name", "role"} == set(dev[0])

    env.app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="production", auth_mode="jwt", jwt_secret=JWT_SECRET
    )
    assert env.client.get("/api/v1/auth/demo-accounts").json() == []


# ---- settings safety


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"auth_mode": "demo"}, "AUTH_MODE"),
        ({"jwt_secret": "short"}, "JWT_SECRET"),
        ({"jwt_secret": "dev-only-" + "x" * 40}, "JWT_SECRET"),
        ({"neo4j_password": "change-me-dev-only"}, "NEO4J_PASSWORD"),
    ],
)
def test_production_refuses_unsafe_settings(kwargs: dict[str, str], fragment: str) -> None:
    good = {
        "app_env": "production",
        "auth_mode": "jwt",
        "jwt_secret": "s" * 40,
        "neo4j_password": "a-real-one",
    }
    with pytest.raises(RuntimeError, match=fragment):
        Settings(**{**good, **kwargs}).check_safe_to_run()  # type: ignore[arg-type]


def test_production_accepts_safe_settings_and_development_is_not_checked() -> None:
    Settings(
        app_env="production", auth_mode="jwt", jwt_secret="s" * 40, neo4j_password="a-real-one"
    ).check_safe_to_run()
    Settings(app_env="development", auth_mode="demo").check_safe_to_run()
