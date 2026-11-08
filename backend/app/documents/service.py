"""Document ingestion and retrieval."""

import hashlib
from pathlib import Path

from app.core.errors import BadRequestError
from app.documents.chunking import chunk_markdown
from app.documents.models import ChunkHit, DocumentRecord
from app.documents.repository import DocumentRepository
from app.llm.base import LLMProvider


class DocumentService:
    def __init__(
        self,
        repo: DocumentRepository,
        llm: LLMProvider,
        *,
        query_prefix: str = "",
        document_prefix: str = "",
        default_k: int = 4,
        dimensions: int = 768,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self._default_k = default_k
        self._dimensions = dimensions

    async def search(self, question: str, k: int | None = None) -> list[ChunkHit]:
        """Find the playbook passages closest in meaning to the question."""
        [vector] = await self._llm.embed([self._query_prefix + question])
        self._check_dimensions(vector)
        return await self._repo.search(vector, k or self._default_k)

    async def ingest_markdown(self, path: Path, kind: str = "playbook") -> int:
        """Chunk, embed and store one Markdown file. Returns the number of chunks."""
        text = path.read_text(encoding="utf-8")
        doc_id = f"{kind}-{path.stem}"
        title, chunks = chunk_markdown(doc_id, text)
        if not chunks:
            raise BadRequestError(f"{path.name} has no content to index.")
        embeddings: list[list[float]] = []
        for start in range(0, len(chunks), 16):
            batch = chunks[start : start + 16]
            texts = [f"{self._document_prefix}{title}. {c.heading}. {c.text}" for c in batch]
            embeddings.extend(await self._llm.embed(texts))
        for vector in embeddings:
            self._check_dimensions(vector)
        record = DocumentRecord(
            id=doc_id,
            kind=kind,
            title=title,
            filename=path.name,
            content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
        )
        await self._repo.replace_document(record, chunks, embeddings)
        return len(chunks)

    def _check_dimensions(self, vector: list[float]) -> None:
        if len(vector) != self._dimensions:
            raise BadRequestError(
                f"The embedding model returned {len(vector)} numbers but the vector index expects "
                f"{self._dimensions}. Check LLM_EMBED_MODEL and EMBED_DIMENSIONS."
            )
