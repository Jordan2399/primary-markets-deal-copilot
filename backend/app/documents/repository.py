"""Document and chunk persistence, including the vector search."""

from typing import Any, Protocol

from neo4j import AsyncManagedTransaction

from app.db.neo4j import Neo4jClient, run_in_tx
from app.documents.chunking import ChunkSpec
from app.documents.models import ChunkHit, DocumentRecord

DELETE_CHUNKS = "MATCH (:Document {id: $doc_id})-[:HAS_CHUNK]->(k:Chunk) DETACH DELETE k"

UPSERT_DOCUMENT = """
MERGE (d:Document {id: $doc_id})
SET d.kind = $kind, d.title = $title, d.filename = $filename, d.hash = $hash
WITH d
UNWIND $chunks AS c
CREATE (k:Chunk {id: c.id, position: c.position, heading: c.heading, text: c.text,
                 embedding: c.embedding})
CREATE (d)-[:HAS_CHUNK]->(k)
"""

# Cosine similarity search through the vector index. Neo4j scores are between 0 and 1.
VECTOR_SEARCH = """
CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding) YIELD node, score
MATCH (d:Document)-[:HAS_CHUNK]->(node)
RETURN node.id AS chunk_id, d.id AS doc_id, d.title AS doc_title, node.heading AS heading,
       node.text AS text, score
ORDER BY score DESC
"""

COUNT_CHUNKS = "MATCH (k:Chunk) RETURN count(k) AS n"


class DocumentRepository(Protocol):
    async def replace_document(
        self, record: DocumentRecord, chunks: list[ChunkSpec], embeddings: list[list[float]]
    ) -> None: ...

    async def search(self, embedding: list[float], k: int) -> list[ChunkHit]: ...

    async def count_chunks(self) -> int: ...


class Neo4jDocumentRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def replace_document(
        self, record: DocumentRecord, chunks: list[ChunkSpec], embeddings: list[list[float]]
    ) -> None:
        rows: list[dict[str, Any]] = [
            {
                "id": c.id,
                "position": c.position,
                "heading": c.heading,
                "text": c.text,
                "embedding": e,
            }
            for c, e in zip(chunks, embeddings, strict=True)
        ]

        async def work(tx: AsyncManagedTransaction) -> None:
            await run_in_tx(tx, DELETE_CHUNKS, {"doc_id": record.id})
            await run_in_tx(
                tx,
                UPSERT_DOCUMENT,
                {
                    "doc_id": record.id,
                    "kind": record.kind,
                    "title": record.title,
                    "filename": record.filename,
                    "hash": record.content_hash,
                    "chunks": rows,
                },
            )

        await self._db.execute_write(work)

    async def search(self, embedding: list[float], k: int) -> list[ChunkHit]:
        rows = await self._db.read(VECTOR_SEARCH, {"k": k, "embedding": embedding})
        return [ChunkHit(**r) for r in rows]

    async def count_chunks(self) -> int:
        rows = await self._db.read(COUNT_CHUNKS)
        return int(rows[0]["n"]) if rows else 0
