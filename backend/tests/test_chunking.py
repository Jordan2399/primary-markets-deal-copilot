from app.documents.chunking import chunk_markdown, split_title

PAGE = """# Pricing

Intro sentence.

## Final price

Paragraph one about price.

## Final terms

Paragraph about terms.
"""


def test_split_title() -> None:
    assert split_title(PAGE)[0] == "Pricing"
    assert split_title("no heading here")[0] == "Untitled"


def test_one_chunk_per_section_with_overview() -> None:
    title, chunks = chunk_markdown("doc", PAGE)
    assert title == "Pricing"
    assert [c.heading for c in chunks] == ["Overview", "Final price", "Final terms"]
    assert [c.id for c in chunks] == ["doc#0", "doc#1", "doc#2"]
    assert chunks[1].text == "Paragraph one about price."


def test_long_sections_are_split_on_paragraphs() -> None:
    paragraphs = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(8))
    _, chunks = chunk_markdown("doc", f"# T\n\n## Long\n\n{paragraphs}", max_chars=700)
    assert len(chunks) > 1
    assert all(len(c.text) <= 700 for c in chunks)
    assert {c.heading for c in chunks} == {"Long"}


def test_empty_sections_are_skipped() -> None:
    _, chunks = chunk_markdown("doc", "# T\n\n## Empty\n\n## Full\n\ntext")
    assert [c.heading for c in chunks] == ["Full"]
