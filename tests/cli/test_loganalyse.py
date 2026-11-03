import json
from pathlib import Path

import pytest

from app.cli.loganalyse import main

FIXTURE = Path(__file__).parent.parent / "fixtures" / "messy.log"


def test_main_writes_json_summary(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(FIXTURE), "--top", "3"])

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert summary["bad_lines"]["count"] == 11
    assert len(summary["top_errors"]) == 3
    assert summary["time_range"] == {"start": "2026-03-02T08:00:04", "end": "2026-03-02T11:30:15"}


def test_main_writes_summary_to_output_file(tmp_path: Path) -> None:
    output = tmp_path / "summary.json"

    exit_code = main([str(FIXTURE), "--output", str(output)])

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["parsed_lines"] == 461


def test_main_missing_file_returns_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(tmp_path / "missing.log")])

    assert exit_code == 1
    assert capsys.readouterr().out == ""


def test_main_rejects_non_positive_top() -> None:
    with pytest.raises(SystemExit):
        main([str(FIXTURE), "--top", "0"])
