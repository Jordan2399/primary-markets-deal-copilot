"""Signed session tokens (JWT, HS256).

The token carries the username, role and an expiry. The server signs it with JWT_SECRET, so
nobody can change the role without the secret. Limit: a token stays valid until it expires,
even if the user is disabled meanwhile (the TTL is short for that reason).
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.errors import UnauthorizedError

ALGORITHM = "HS256"
ISSUER = "deal-copilot"


def issue_token(
    *, username: str, role: str, display_name: str, secret: str, ttl_minutes: int
) -> str:
    """Create a signed token for a user. The role inside it is what the API trusts later."""
    now = datetime.now(UTC)
    # Standard JWT claim names: iss issuer, sub subject, iat issued-at, exp expiry, jti unique id.
    claims = {
        "iss": ISSUER,
        "sub": username,
        "role": role,
        "name": display_name,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": uuid.uuid4().hex,  # unique per token, so a token can be identified in logs
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> dict[str, str]:
    """Check signature, issuer and expiry; return the claims or raise UnauthorizedError."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],  # never accept the algorithm named in the token itself
            issuer=ISSUER,  # reject tokens made by some other system with the same secret
            # A token missing any of these claims is refused even if the signature is fine.
            options={"require": ["exp", "sub", "role", "iss"]},
        )
    # Expired gets its own message so the UI can ask the user to sign in again.
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired. Please sign in again.") from exc
    # Any other problem (bad signature, wrong issuer, garbage) gets one generic message.
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Your session is not valid. Please sign in again.") from exc
    return {k: str(v) for k, v in claims.items()}
