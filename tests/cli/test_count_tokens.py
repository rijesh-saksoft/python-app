from pathlib import Path

import pytest

from app.cli import count_tokens as cli
from app.config import Settings
from app.services.llm_client import LlmUnavailableError


def test_run_refuses_an_empty_folder_before_calling_a_model(tmp_path: Path) -> None:
    assert cli.main(["--input-dir", str(tmp_path)]) == 1


def test_run_reports_an_unavailable_model_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "prose.txt").write_text("hello world", encoding="utf-8")

    def unavailable(*_: object, **__: object) -> list[object]:
        raise LlmUnavailableError("no model answered: model-a")

    settings = Settings(llm_base_url="http://llm.test/v1/", llm_model="model-a")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "count_tokens", unavailable)

    assert cli.main(["--input-dir", str(tmp_path)]) == 1
