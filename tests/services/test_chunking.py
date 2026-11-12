import pytest

from app.services.chunking import by_section, by_sentences, fixed_size

DOC = """# Expenses Policy

We repay reasonable costs.

## Meals

Meals are claimable away from your site. The limit is 25 per day. Alcohol is never paid.

## Mileage

Journeys are paid at 0.45 per mile.
"""


def test_fixed_size_chunks_overlap_and_cover_the_whole_text() -> None:
    chunks = fixed_size("expenses.md", DOC, size=60, overlap=20)

    assert all(len(chunk.text) <= 60 for chunk in chunks)
    assert chunks[0].text == DOC[:60]
    assert chunks[1].text.startswith(DOC[40:60])
    assert DOC.endswith(chunks[-1].text)


def test_fixed_size_refuses_an_overlap_as_large_as_the_chunk() -> None:
    with pytest.raises(ValueError, match="overlap"):
        fixed_size("expenses.md", DOC, size=50, overlap=50)


def test_section_chunks_keep_the_title_and_heading_with_the_text() -> None:
    chunks = by_section("expenses.md", DOC)

    assert [chunk.text.splitlines()[0] for chunk in chunks] == [
        "Expenses Policy",
        "Expenses Policy - Meals",
        "Expenses Policy - Mileage",
    ]
    assert "The limit is 25 per day." in chunks[1].text


def test_sentence_chunks_never_split_a_sentence() -> None:
    chunks = by_sentences("expenses.md", DOC, per_chunk=2)

    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert any("The limit is 25 per day." in chunk.text for chunk in chunks)
    assert "#" not in " ".join(chunk.text for chunk in chunks)


def test_chunks_record_their_document_and_position() -> None:
    chunks = by_section("expenses.md", DOC)

    assert [(chunk.doc, chunk.index) for chunk in chunks] == [
        ("expenses.md", 0),
        ("expenses.md", 1),
        ("expenses.md", 2),
    ]
