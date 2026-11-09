"""Document and retrieval models."""

from dataclasses import dataclass

from pydantic import BaseModel


class ChunkHit(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    heading: str
    text: str
    score: float


@dataclass(frozen=True)
class DocumentRecord:
    id: str
    kind: str
    title: str
    filename: str
    content_hash: str
