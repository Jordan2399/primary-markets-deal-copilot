"""Thin wrapper around the Neo4j async driver.

Repositories use `read`, `write` and `execute_write`; nothing outside `app.db` and the
repository classes talks to the driver. Queries always pass parameters, never string
concatenation, so user input cannot change the meaning of a query.
"""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncManagedTransaction

T = TypeVar("T")


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        self._database = database
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def verify(self) -> None:
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        await self._driver.close()

    async def read(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async def work(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
            result = await tx.run(query, params or {})
            return await result.data()

        async with self._driver.session(database=self._database) as session:
            return await session.execute_read(work)

    async def write(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async def work(tx: AsyncManagedTransaction) -> list[dict[str, Any]]:
            result = await tx.run(query, params or {})
            return await result.data()

        return await self.execute_write(work)

    async def execute_write(self, work: Callable[[AsyncManagedTransaction], Awaitable[T]]) -> T:
        """Run several statements in ONE transaction: all succeed or none do."""
        async with self._driver.session(database=self._database) as session:
            return await session.execute_write(work)

    async def run_auto(self, query: str) -> None:
        """Auto-commit statement, used for schema changes (constraints and indexes)."""
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query)
            await result.consume()


async def run_in_tx(
    tx: AsyncManagedTransaction, query: str, params: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Run one statement inside a transaction function and return its rows."""
    result = await tx.run(query, params or {})
    return await result.data()
