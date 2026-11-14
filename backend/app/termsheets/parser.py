"""Read an uploaded term sheet into plain text. Everything happens in memory."""

import io

from app.core.errors import BadRequestError
from app.termsheets.cleaning import clean_pages

MAX_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 40  # Final Terms are usually 10-30 pages; longer files are base prospectuses
MAX_CHARS = 80_000  # ceiling for the stored text; the model gets a focused part of it
ALLOWED_SUFFIXES = (".txt", ".md", ".pdf")


def read_text(filename: str, content: bytes) -> str:
    """Read an uploaded .txt, .md or .pdf into clean text (PDFs also lose headers and wrapping)."""
    name = filename.lower()
    if not name.endswith(ALLOWED_SUFFIXES):
        raise BadRequestError("Only .txt, .md and .pdf files are accepted.")
    if len(content) > MAX_BYTES:
        raise BadRequestError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if name.endswith(".pdf"):
        text = _pdf_text(content)
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BadRequestError("The text file is not valid UTF-8.") from exc
    return clean_text(text)


def clean_text(text: str) -> str:
    """Basic tidy for any text source: drop NUL bytes, refuse empty input, cap the length."""
    text = text.replace("\x00", "").strip()
    if not text:
        raise BadRequestError("The document contains no text. Scanned PDFs are not supported.")
    return text[:MAX_CHARS]


def _pdf_text(content: bytes) -> str:
    """Extract text page by page, then clean it (headers, footers, page numbers, wrapped lines)."""
    if not content.startswith(b"%PDF"):
        raise BadRequestError("The file is not a real PDF.")
    import pdfplumber  # imported here so the rest of the app starts without it

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise BadRequestError(f"The PDF has more than {MAX_PDF_PAGES} pages.")
            pages = [(page.extract_text() or "") for page in pdf.pages]
        # Cleaning needs the page boundaries to spot a header that repeats on every page.
        return clean_pages(pages)
    except BadRequestError:
        raise
    except Exception as exc:  # noqa: BLE001 - a damaged PDF must be a clean 400, not a 500
        raise BadRequestError("The PDF could not be read.") from exc
