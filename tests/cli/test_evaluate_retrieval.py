import json
from pathlib import Path

from app.cli.evaluate_retrieval import main


def test_run_refuses_unlabelled_questions_before_calling_a_model(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "leave.md").write_text("# Leave\n\nYou get 24 days.", encoding="utf-8")
    questions = tmp_path / "questions.json"
    questions.write_text(
        json.dumps([{"id": "q1", "question": "How many days?", "expected_docs": []}]),
        encoding="utf-8",
    )

    exit_code = main(["--docs-dir", str(docs), "--questions", str(questions)])

    assert exit_code == 1
