"""Term sheet storage."""

import json
from datetime import datetime
from typing import Protocol

from neo4j import AsyncManagedTransaction

from app.audit.models import AuditEvent
from app.audit.repository import write_in_tx
from app.db.neo4j import Neo4jClient, run_in_tx
from app.termsheets.models import StoredTermSheet, TermSheetRecord

CREATE = """
CREATE (d:Document {
  id: $id, kind: 'termsheet', title: $filename, filename: $filename, content_hash: $content_hash,
  deal_id: $deal_id, text: $text, extraction: $extraction, method: $method, model: $model,
  extracted_by: $extracted_by, extracted_at: datetime($extracted_at)})
"""

LINK = """
MATCH (d:Document {id: $id}), (deal:Deal {id: $deal_id})
CREATE (deal)-[:HAS_DOCUMENT]->(d)
"""

GET = """
MATCH (d:Document {id: $id, kind: 'termsheet'})
RETURN d.id AS id, d.filename AS filename, d.deal_id AS deal_id, d.content_hash AS content_hash,
       d.text AS text, d.extraction AS extraction, d.method AS method, d.model AS model,
       d.extracted_by AS extracted_by, toString(d.extracted_at) AS extracted_at
"""


class TermSheetRepository(Protocol):
    async def save(self, doc: StoredTermSheet, event: AuditEvent) -> None: ...
    async def get(self, doc_id: str) -> StoredTermSheet | None: ...


class Neo4jTermSheetRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def save(self, doc: StoredTermSheet, event: AuditEvent) -> None:
        params = {
            "id": doc.id,
            "filename": doc.filename,
            "content_hash": doc.content_hash,
            "deal_id": doc.deal_id,
            "text": doc.text,
            "extraction": doc.record.model_dump_json(),
            "method": doc.method,
            "model": doc.model,
            "extracted_by": doc.extracted_by,
            "extracted_at": doc.extracted_at.isoformat(),
        }

        async def work(tx: AsyncManagedTransaction) -> None:
            await run_in_tx(tx, CREATE, params)
            if doc.deal_id:
                await run_in_tx(tx, LINK, {"id": doc.id, "deal_id": doc.deal_id})
            await write_in_tx(tx, event)

        await self._db.execute_write(work)

    async def get(self, doc_id: str) -> StoredTermSheet | None:
        rows = await self._db.read(GET, {"id": doc_id})
        if not rows:
            return None
        r = rows[0]
        return StoredTermSheet(
            id=r["id"],
            filename=r["filename"],
            deal_id=r["deal_id"],
            content_hash=r["content_hash"],
            text=r["text"],
            record=TermSheetRecord(**json.loads(r["extraction"])),
            method=r["method"],
            model=r["model"],
            extracted_by=r["extracted_by"],
            extracted_at=datetime.fromisoformat(r["extracted_at"]),
        )
