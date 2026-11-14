"""Conversations: persistence.

Every query that touches a conversation also matches its `owner`, so one user can never read,
rename or delete another user's thread, even by guessing an id.
"""

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from neo4j import AsyncManagedTransaction

from app.audit.models import AuditEvent
from app.audit.repository import write_in_tx
from app.conversations.models import ConversationDetail, ConversationSummary, StoredMessage
from app.copilot.models import Source
from app.db.neo4j import Neo4jClient, run_in_tx

# Columns for a sidebar row. toString turns Neo4j datetimes into text the API can send as JSON.
SUMMARY = """
c.id AS id, c.title AS title, c.deal_id AS deal_id, toString(c.created_at) AS created_at,
toString(c.updated_at) AS updated_at, c.message_count AS message_count
"""

# The owner is in every MATCH below: that is the whole access-control rule for threads.
LIST = f"""
MATCH (c:Conversation {{owner: $owner}})
RETURN {SUMMARY} ORDER BY c.updated_at DESC LIMIT $limit
"""
GET = f"MATCH (c:Conversation {{id: $id, owner: $owner}}) RETURN {SUMMARY}"
# Newest first with a LIMIT, so 'the last N messages' is cheap; Python reverses to oldest first.
MESSAGES = """
MATCH (:Conversation {id: $id, owner: $owner})-[:HAS_MESSAGE]->(m:Message)
RETURN m.id AS id, m.role AS role, m.content AS content, toString(m.created_at) AS created_at,
       m.sources AS sources, m.cited AS cited, m.intent AS intent, m.audit_id AS audit_id
ORDER BY m.seq DESC LIMIT $limit
"""
# Change the title only when the id and the owner both match.
RENAME = """
MATCH (c:Conversation {id: $id, owner: $owner}) SET c.title = $title RETURN c.id AS id
"""
# Create the conversation on the first answer, then add the question and the answer to it.
# If the id exists but belongs to someone else, the WHERE stops everything and nothing is written.
APPEND_TURN = """
MERGE (c:Conversation {id: $id})
ON CREATE SET c.owner = $owner, c.title = $title, c.created_at = datetime($now), c.message_count = 0
WITH c WHERE c.owner = $owner
SET c.updated_at = datetime($now), c.deal_id = $deal_id
WITH c, c.message_count AS before
UNWIND range(0, size($messages) - 1) AS i
WITH c, before, i, $messages[i] AS m
CREATE (c)-[:HAS_MESSAGE]->(:Message {
  id: m.id, seq: before + i + 1, role: m.role, content: m.content, created_at: datetime($now),
  sources: m.sources, cited: m.cited, intent: m.intent, audit_id: m.audit_id})
WITH c, count(*) AS added
SET c.message_count = c.message_count + added
RETURN c.id AS id
"""
# Delete the messages first (FOREACH), then the conversation, only for the owner.
DELETE = """
MATCH (c:Conversation {id: $id, owner: $owner})
OPTIONAL MATCH (c)-[:HAS_MESSAGE]->(m:Message)
WITH c, collect(m) AS ms
FOREACH (x IN ms | DETACH DELETE x)
DETACH DELETE c
RETURN 1 AS deleted
"""


def _message(row: dict[str, Any]) -> StoredMessage:
    """Rebuild a StoredMessage from a row. Sources were saved as a JSON string."""
    sources = json.loads(row["sources"]) if row.get("sources") else []
    return StoredMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        created_at=row.get("created_at") or "",
        sources=[Source.model_validate(s) for s in sources],
        cited=list(row.get("cited") or []),
        intent=row.get("intent"),
        audit_id=row.get("audit_id"),
    )


class ConversationRepository(Protocol):
    """Storage contract for threads; tests use an in-memory fake with the same methods."""

    async def list_owned(self, owner: str, limit: int) -> list[ConversationSummary]: ...
    async def get(self, conversation_id: str, owner: str) -> ConversationDetail | None: ...
    async def recent_messages(
        self, conversation_id: str, owner: str, limit: int
    ) -> list[StoredMessage]: ...
    async def append_turn(
        self,
        conversation_id: str,
        owner: str,
        deal_id: str | None,
        title: str,
        messages: list[StoredMessage],
    ) -> bool: ...
    async def rename(self, conversation_id: str, owner: str, title: str) -> bool: ...
    async def delete(self, conversation_id: str, owner: str, event: AuditEvent) -> bool: ...


class Neo4jConversationRepository:
    """Neo4j implementation of the thread storage."""

    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def list_owned(self, owner: str, limit: int) -> list[ConversationSummary]:
        """Summaries of the owner's threads, newest activity first."""
        rows = await self._db.read(LIST, {"owner": owner, "limit": limit})
        return [ConversationSummary(**row) for row in rows]

    async def get(self, conversation_id: str, owner: str) -> ConversationDetail | None:
        """The thread with up to 500 messages, or None if missing or owned by someone else."""
        params = {"id": conversation_id, "owner": owner}
        rows = await self._db.read(GET, params)
        if not rows:
            return None
        # Fetched newest-first, then reversed so the UI shows the oldest message at the top.
        newest_first = await self._db.read(MESSAGES, {**params, "limit": 500})
        messages = [_message(row) for row in reversed(newest_first)]
        return ConversationDetail(**rows[0], messages=messages)

    async def recent_messages(
        self, conversation_id: str, owner: str, limit: int
    ) -> list[StoredMessage]:
        """The last `limit` messages, oldest first: the history given to the follow-up rewrite."""
        rows = await self._db.read(
            MESSAGES, {"id": conversation_id, "owner": owner, "limit": limit}
        )
        return [_message(row) for row in reversed(rows)]

    async def append_turn(
        self,
        conversation_id: str,
        owner: str,
        deal_id: str | None,
        title: str,
        messages: list[StoredMessage],
    ) -> bool:
        """Create the thread if new, and append the messages. False when the id is not theirs."""
        # Neo4j cannot store nested maps as properties, so sources are saved as a JSON string.
        payload = [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": json.dumps([s.model_dump() for s in m.sources]),
                "cited": m.cited,
                "intent": m.intent,
                "audit_id": m.audit_id,
            }
            for m in messages
        ]
        rows = await self._db.write(
            APPEND_TURN,
            {
                "id": conversation_id,
                "owner": owner,
                "title": title,
                "deal_id": deal_id,
                "now": datetime.now(UTC).isoformat(),
                "messages": payload,
            },
        )
        return bool(rows)

    async def rename(self, conversation_id: str, owner: str, title: str) -> bool:
        """True when a thread owned by `owner` was renamed."""
        rows = await self._db.write(RENAME, {"id": conversation_id, "owner": owner, "title": title})
        return bool(rows)

    async def delete(self, conversation_id: str, owner: str, event: AuditEvent) -> bool:
        """Delete the thread and write the audit event in one transaction (both or neither)."""

        async def work(tx: AsyncManagedTransaction) -> bool:
            rows = await run_in_tx(tx, DELETE, {"id": conversation_id, "owner": owner})
            if not rows:
                return False
            await write_in_tx(tx, event)
            return True

        return await self._db.execute_write(work)
