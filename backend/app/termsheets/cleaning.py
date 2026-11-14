"""Clean text read from a long PDF and find the part that holds the deal terms.

Real Final Terms are 10-100 pages of legal text. Sending all of it to a small local model makes it
return empty fields, so two steps happen before extraction:

1. `clean_pages` removes what is not content: running headers and footers, page numbers, and the
   hyphens and line breaks the PDF layout put inside sentences.
2. `focus_terms` keeps only the passages around the term-sheet keywords (amount, currency, coupon,
   dates...), so the model reads a few thousand characters instead of the whole document.

Both are plain functions on text, so they are tested without a PDF or a model.
"""

import re
from collections import Counter

# A page whose only content is a number, "Page 3", "3 / 12" or "- 3 -" is just a page marker.
_PAGE_NUMBER = re.compile(
    r"^\s*(?:page\s+)?[-–]?\s*\d{1,3}\s*(?:(?:/|of)\s*\d{1,3})?\s*[-–]?\s*$", re.I
)

# A line is a header/footer candidate only if it sits within this many lines of a page edge.
_EDGE_LINES = 3

# A line counts as repeated when it appears on at least this share of the pages (3+ pages only).
_REPEAT_SHARE = 0.5

# Documents at or below this size go to the model whole; focusing would only lose context.
FOCUS_THRESHOLD = 6_000

# Hard ceiling for what is sent to the model after focusing.
FOCUS_MAX_CHARS = 8_000

# How much text to keep before and after each keyword hit, and from the start of the document
# (the cover page usually names the issuer and the notes).
_WINDOW_BEFORE = 150
_WINDOW_AFTER = 450
_COVER_CHARS = 1_500

# Words that introduce the facts we extract. Matching is case-insensitive.
_ANCHORS = re.compile(
    r"issuer|isin|specified currency|currency|aggregate nominal amount|principal amount|"
    r"issue size|rate of interest|interest rate|coupon|issue date|settlement date|"
    r"maturity date|listing|admission to trading|governing law|selling restrictions|"
    r"regulation s|rule 144a|issue of|notes due|per cent",
    re.I,
)


# A line shaped like "9. Governing law: English law" or "Issuer: Example".
_LABEL_ROW = re.compile(r"^(?:\(?[0-9ivx]+[.)]\s+)?[A-Za-z][A-Za-z /()',-]{1,60}:\s+\S")

# PDF lines shorter than this were ended by the author, not wrapped by the layout.
_WRAP_WIDTH = 70


def _normalise_line(line: str) -> str:
    """Key used to recognise the same header on different pages (digits and spaces ignored)."""
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().lower()))


def clean_pages(pages: list[str]) -> str:
    """Join the text of all pages after removing headers, footers and page numbers."""
    split = [page.splitlines() for page in pages]

    # Count how many pages each edge line appears on (once per page, even if repeated).
    seen: Counter[str] = Counter()
    for lines in split:
        edges = lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]
        for key in {_normalise_line(line) for line in edges if line.strip()}:
            seen[key] += 1

    # With fewer than 3 pages "repeated" means nothing, so no header detection is done.
    threshold = max(2, int(len(pages) * _REPEAT_SHARE + 0.5)) if len(pages) >= 3 else None

    kept_pages: list[str] = []
    for lines in split:
        kept: list[str] = []
        for index, line in enumerate(lines):
            # Very short pages have no real header/footer zone: everything on them is content.
            at_edge = len(lines) > 2 * _EDGE_LINES and (
                index < _EDGE_LINES or index >= len(lines) - _EDGE_LINES
            )
            if _PAGE_NUMBER.match(line):
                continue
            if at_edge and threshold and seen[_normalise_line(line)] >= threshold:
                continue
            kept.append(line.rstrip())
        kept_pages.append("\n".join(kept))
    return join_wrapped_lines("\n".join(kept_pages))


def join_wrapped_lines(text: str) -> str:
    """Undo PDF line wrapping: re-join hyphenated words and glue continuation lines.

    A line that ends a sentence, or that looks like a "Label: value" row, a numbered row or a
    heading, keeps its line break. Other lines are joined to the next one with a space.
    """
    # "Aggre-\ngate" -> "Aggregate" (only a hyphen between lowercase letters, so ISINs and
    # "5-year" are left alone).
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)

    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")  # keep one blank line between blocks
            continue
        if out and out[-1] != "" and _continues_previous(out[-1], line):
            out[-1] = f"{out[-1]} {line}"
        else:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _continues_previous(previous: str, line: str) -> bool:
    """True when `line` is the second half of a sentence that `previous` started."""
    if previous.endswith((".", ":", ";", "!", "?")):
        return False
    # A new numbered row ("3. Specified Currency") or "Label: value" row starts a fresh line.
    if re.match(r"^(\(?[0-9ivx]+[.)]|[A-Z][A-Za-z /()'-]{2,60}:)\s", line):
        return False
    # A short all-caps line is a heading.
    if line.isupper() and len(line) < 60:
        return False
    # A short "Label: value" row was not wrapped (a wrapped row fills the line width), so the
    # next line is a new sentence, not its continuation.
    if _LABEL_ROW.match(previous) and len(previous) < _WRAP_WIDTH:
        return False
    return True


# Where each required field is usually stated. Used to read only the passages for missing fields.
_FIELD_ANCHORS: dict[str, re.Pattern[str]] = {
    "issuer": re.compile(r"issuer|issue of|\bby\b.{0,60}\(the", re.I),
    "isin": re.compile(r"isin|common code|\b[A-Z]{2}[A-Z0-9]{9}\d\b"),
    "currency": re.compile(r"specified currency|currency|issue of", re.I),
    "size_mm": re.compile(
        r"aggregate nominal amount|principal amount|issue size|issue of|nominal amount", re.I
    ),
    "coupon_pct": re.compile(
        r"rate of interest|interest rate|interest basis|coupon|per cent", re.I
    ),
    "maturity": re.compile(r"maturity date|notes due|maturity", re.I),
}

# The model is only asked about the gaps, so a much smaller excerpt is enough.
GAP_MAX_CHARS = 3_000
_GAP_COVER_CHARS = 600


def focus_fields(text: str, fields: list[str]) -> str:
    """Excerpt for the model holding only the passages for `fields`, plus a short cover.

    Unlike `focus_terms` (every keyword in the document), this looks for the keywords of the
    missing fields only, so the model reads about 3,000 characters instead of 8,000.
    """
    spans = [(0, min(_GAP_COVER_CHARS, len(text)))]
    for field in fields:
        pattern = _FIELD_ANCHORS.get(field)
        if pattern is None:
            continue
        for match in pattern.finditer(text):
            spans.append((max(0, match.start() - 100), min(len(text), match.end() + 350)))
    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    excerpt = "\n...\n".join(text[s:e].strip() for s, e in merged)
    return excerpt[:GAP_MAX_CHARS]


def focus_terms(text: str) -> tuple[str, bool]:
    """Return (text for the model, whether it was shortened).

    Short documents are returned whole. Long ones are reduced to the cover plus the passages around
    the anchor words, in document order, without repeating overlapping passages.
    """
    if len(text) <= FOCUS_THRESHOLD:
        return text, False

    # Build [start, end) windows around each hit, then merge windows that touch or overlap.
    spans = [(0, min(_COVER_CHARS, len(text)))]
    for match in _ANCHORS.finditer(text):
        spans.append(
            (max(0, match.start() - _WINDOW_BEFORE), min(len(text), match.end() + _WINDOW_AFTER))
        )
    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    pieces = [text[start:end].strip() for start, end in merged]
    focused = "\n...\n".join(pieces)
    if len(focused) > FOCUS_MAX_CHARS:
        focused = focused[:FOCUS_MAX_CHARS]
    # If focusing kept nearly everything there is no point calling it "shortened".
    return focused, len(focused) < len(text) * 0.95
