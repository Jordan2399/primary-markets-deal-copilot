"""Split a Markdown page into chunks for retrieval.

Strategy: one chunk per `##` section (a section is usually one idea), and any section longer
than `max_chars` is split on blank lines. Each chunk keeps its section heading, so an answer
can cite "Pricing > Final terms" and not just "chunk 3". Small, focused chunks retrieve better
than whole pages and keep the prompt short, which matters on an 8 GB GPU.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkSpec:
    id: str
    position: int
    heading: str
    text: str


def split_title(markdown: str) -> tuple[str, str]:
    """Return (title, body). The title is the first `# ` heading, if any."""
    match = re.match(r"\s*#\s+(.+?)\s*\n", markdown)
    if not match:
        return "Untitled", markdown.strip()
    return match.group(1).strip(), markdown[match.end() :].strip()


def _sections(body: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", body)
    sections: list[tuple[str, str]] = []
    intro = parts[0].strip()
    if intro:
        sections.append(("Overview", intro))
    for index in range(1, len(parts), 2):
        text = parts[index + 1].strip()
        if text:
            sections.append((parts[index].strip(), text))
    return sections


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) > max_chars and current:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(
    doc_id: str, markdown: str, max_chars: int = 1100
) -> tuple[str, list[ChunkSpec]]:
    title, body = split_title(markdown)
    chunks: list[ChunkSpec] = []
    for heading, text in _sections(body):
        for piece in _split_long(text, max_chars):
            position = len(chunks)
            chunks.append(ChunkSpec(f"{doc_id}#{position}", position, heading, piece))
    return title, chunks
