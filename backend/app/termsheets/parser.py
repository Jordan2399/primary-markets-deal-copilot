"""Read an uploaded term sheet into plain text. Everything happens in memory."""

import io

from app.core.errors import BadRequestError

MAX_BYTES = 2 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_CHARS = 30_000
ALLOWED_SUFFIXES = (".txt", ".md", ".pdf")


def read_text(filename: str, content: bytes) -> str:
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
    text = text.replace("\x00", "").strip()
    if not text:
        raise BadRequestError("The document contains no text. Scanned PDFs are not supported.")
    return text[:MAX_CHARS]


def _pdf_text(content: bytes) -> str:
    if not content.startswith(b"%PDF"):
        raise BadRequestError("The file is not a real PDF.")
    import pdfplumber  # imported here so the rest of the app starts without it

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise BadRequestError(f"The PDF has more than {MAX_PDF_PAGES} pages.")
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    except BadRequestError:
        raise
    except Exception as exc:  # noqa: BLE001 - a damaged PDF must be a clean 400, not a 500
        raise BadRequestError("The PDF could not be read.") from exc
