# Day 3a: term sheet lab for real documents

## What changed

| Area | Before | Now |
| --- | --- | --- |
| Input | Text box and file input at the same time; the file silently won | A switch: **Paste text** or **Upload file**. Leaving a mode clears its input. The API refuses both at once (400) |
| PDF reading | Raw text of up to 20 pages | Up to 40 pages; running headers, footers and page numbers removed; hyphenated and wrapped lines joined |
| What the model reads | The first 30,000 characters | The cover plus the passages around the term keywords (issuer, ISIN, currency, amount, coupon, dates, listing, law). Short documents are sent whole |
| Rules fallback | `Label: value` lines only | Also numbered rows ("3. Specified Currency"), longer legal names, "3.750 per cent.", and values on the line after the label |
| Feedback | "X is missing" in the check list | The result names the source (text or file), says when only the terms passages were read, and lists the fields not found |
| Default deal | `D-2026-008` hard-coded | No deal preselected |

## Where the code is

- `backend/app/termsheets/cleaning.py`: `clean_pages`, `join_wrapped_lines`, `focus_terms`.
- `backend/app/termsheets/parser.py`: calls `clean_pages` for PDFs.
- `backend/app/termsheets/rules.py`: label synonyms, row-number stripping, next-line values, `per cent`.
- `backend/app/termsheets/service.py`: one-source rule, focusing, `not_found`.
- `backend/tests/test_termsheet_pdf.py`: generates Final Terms-style PDFs with reportlab (header, footer, numbered rows, wrapped value, filler pages).
- `frontend/app/termsheets/page.tsx`: the switch, file chip, result notes.

## How to explain it

"Real Final Terms are long legal text. A small local model loses the facts in it, so the code first cleans the PDF and cuts it down to the passages around the term keywords. Rules read the same text as a safety net. The model never decides whether the document is right: validation and the booking diff are plain code, and the page says which fields it could not find."

## Try it

1. Term sheets, **Upload file**, choose a Final Terms PDF, **Extract and validate**.
2. Check the note "The model read the passages with the terms (x of y characters)".
3. Switch to **Paste text**: the file is gone. Paste only two lines (`Issuer: ...`, `Currency: EUR`) and see the "Not found in this document" list.
4. Choose a deal and **Load sample (with errors)** to see the red mismatches as before.

## Honest limits

- Scanned PDFs (images) still fail: there is no OCR.
- A base prospectus (over 40 pages or 2 MB) is refused. This lab is for Final Terms and term sheets.
- Focusing uses keywords, not understanding. An unusual document that never uses these words may lose its terms; the page then lists them as not found.
- Tested with generated PDFs and a fake model. A real file and the real model are the next test.
