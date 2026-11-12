import json
from pathlib import Path

import pytest

from app.cli.evaluate_cvs import main
from app.services.cv_evaluation import FIELDS, CvRun, EvaluationResult


def write_result(path: Path, model: str) -> None:
    run = CvRun(cv_id="cv_01", model=model, fields=dict.fromkeys(FIELDS, True))
    result = EvaluationResult(model=model, prompt_version="cv_extract/v1", runs=[run])
    path.write_text(result.model_dump_json(), encoding="utf-8")


def test_table_combines_saved_results(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_result(tmp_path / "a.json", "hosted-model")
    write_result(tmp_path / "b.json", "local-model")

    exit_code = main(["table", str(tmp_path / "a.json"), str(tmp_path / "b.json")])

    assert exit_code == 0
    assert "| Measure | hosted-model | local-model |" in capsys.readouterr().out


def test_run_refuses_unfilled_gold_before_calling_a_model(tmp_path: Path) -> None:
    inputs, gold = tmp_path / "input", tmp_path / "gold"
    inputs.mkdir()
    gold.mkdir()
    (inputs / "cv_01.txt").write_text("Asha Alder", encoding="utf-8")
    (gold / "cv_01.json").write_text(json.dumps({"name": ""}), encoding="utf-8")

    exit_code = main(["run", "--input-dir", str(inputs), "--gold-dir", str(gold)])

    assert exit_code == 1
