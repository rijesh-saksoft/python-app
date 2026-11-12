import json
from pathlib import Path

import pytest

from app.services.chunking import by_section
from app.services.rag_evaluation import (
    Question,
    QuestionFileError,
    format_table,
    load_questions,
    run_all,
)

DOCS = {
    "meals.md": "# Meals\n\n## Limit\n\nThe meal limit is 25 per day.",
    "hotels.md": "# Hotels\n\n## Limit\n\nThe hotel limit is 150 per night.",
    "leave.md": "# Leave\n\n## Days\n\nYou get 24 days of leave.",
}
VOCAB = ["meal", "hotel", "leave", "limit", "night", "day"]


class WordCountEmbedder:
    """A stand-in for a model: one dimension per vocabulary word, counting its occurrences."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        lower = text.lower()
        return [float(lower.count(word)) + 0.01 for word in VOCAB]


def test_rank_is_the_position_of_the_first_chunk_from_an_expected_doc() -> None:
    questions = [
        Question(id="q1", question="hotel price per night", expected_docs=["hotels.md"]),
        Question(id="q2", question="hotel limit", expected_docs=["meals.md"]),
    ]

    [result] = run_all(DOCS, questions, WordCountEmbedder(), {"by_section": by_section})

    assert [r.rank for r in result.results] == [1, 2]
    assert result.hits_at(1) == 1
    assert result.hits_at(3) == 2
    assert result.results[1].top_docs[0] == "hotels.md"


def test_table_shows_hits_per_k_for_each_chunking() -> None:
    questions = [Question(id="q1", question="leave days", expected_docs=["leave.md"])]
    results = run_all(DOCS, questions, WordCountEmbedder(), {"by_section": by_section})

    assert "| by_section | 3 | " in format_table(results)
    assert "| 1/1 | 1/1 | 1/1 |" in format_table(results)


def write_questions(path: Path, expected_docs: list[str]) -> Path:
    rows = [{"id": "q1", "question": "leave days", "expected_docs": expected_docs}]
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_unlabelled_questions_are_refused(tmp_path: Path) -> None:
    path = write_questions(tmp_path / "questions.json", [])

    with pytest.raises(QuestionFileError, match="q1"):
        load_questions(path, set(DOCS))


def test_labels_naming_an_unknown_document_are_refused(tmp_path: Path) -> None:
    path = write_questions(tmp_path / "questions.json", ["holiday.md"])

    with pytest.raises(QuestionFileError, match=r"holiday\.md"):
        load_questions(path, set(DOCS))
