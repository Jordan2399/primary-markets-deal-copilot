"""Users: persistence."""

from typing import Any, Protocol

from app.auth.models import User
from app.core.security import Role
from app.db.neo4j import Neo4jClient

# The columns every user query returns, in one place so the queries stay in step.
FIELDS = """
u.username AS username, u.display_name AS display_name, u.role AS role,
u.active AS active, u.password_hash AS password_hash
"""

# Read one user by username / list all users (the f-string only inserts the fixed FIELDS text).
GET = f"MATCH (u:User {{username: $username}}) RETURN {FIELDS}"
LIST = f"MATCH (u:User) RETURN {FIELDS} ORDER BY u.username"
# MERGE on the unique key: running the seed twice never overwrites an existing user or password.
CREATE_IF_MISSING = """
MERGE (u:User {username: $username})
ON CREATE SET u.display_name = $display_name, u.role = $role, u.active = true,
              u.password_hash = $password_hash, u.created_at = datetime(), u.created = true
WITH u, coalesce(u.created, false) AS created
REMOVE u.created
RETURN created
"""


def _user(row: dict[str, Any]) -> User:
    """Turn one database row into a User object."""
    return User(
        username=row["username"],
        display_name=row["display_name"],
        role=Role(row["role"]),
        active=bool(row["active"]),
        password_hash=row["password_hash"],
    )


class UserRepository(Protocol):
    """What the service needs from storage. Tests use an in-memory version of this."""

    async def get(self, username: str) -> User | None: ...
    async def all_users(self) -> list[User]: ...
    async def create_if_missing(self, user: User) -> bool: ...


class Neo4jUserRepository:
    """The real implementation, backed by Neo4j."""

    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def get(self, username: str) -> User | None:
        """Return the user or None when the username does not exist."""
        rows = await self._db.read(GET, {"username": username})
        return _user(rows[0]) if rows else None

    async def all_users(self) -> list[User]:
        """Return every user, sorted by username (admin screen)."""
        return [_user(row) for row in await self._db.read(LIST)]

    async def create_if_missing(self, user: User) -> bool:
        """Insert the user only if the username is free. True when a new user was created."""
        rows = await self._db.write(
            CREATE_IF_MISSING,
            {
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role.value,
                "password_hash": user.password_hash,
            },
        )
        return bool(rows and rows[0]["created"])
