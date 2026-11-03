from datetime import datetime
from pathlib import Path

import pytest

from app.services.log_analyser import (
    LogFileError,
    LogLineError,
    analyse_file,
    analyse_lines,
    parse_line,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "messy.log"


def test_parse_line_reads_all_fields() -> None:
    entry = parse_line("2026-03-02T08:00:12 INFO auth login ok user=u101")

    assert entry.timestamp == datetime(2026, 3, 2, 8, 0, 12)
    assert entry.level == "INFO"
    assert entry.module == "auth"
    assert entry.message == "login ok user=u101"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("", "blank line"),
        ("   ", "blank line"),
        ("2026-03-02T11:02", "wrong number of fields"),
        ("2026-03-02T10:15:09 ERROR", "wrong number of fields"),
        ("####### restart #######", "wrong number of fields"),
        ("2026-03-02T09:61:00 INFO api GET /items/4 200 12ms", "invalid timestamp"),
        ('  File "app.py", line 42, in handler', "invalid timestamp"),
        ("2026-03-02T10:15:07 LOUD api shouting is not a level", "unknown level"),
    ],
)
def test_parse_line_rejects_broken_lines(text: str, reason: str) -> None:
    with pytest.raises(LogLineError, match=reason):
        parse_line(text)


def test_analyse_lines_counts_levels_and_errors() -> None:
    lines = [
        "2026-03-02T08:00:00 INFO api ok\n",
        "2026-03-02T08:00:01 ERROR db connection refused\n",
        "2026-03-02T08:00:02 ERROR db connection refused\n",
        "2026-03-02T08:00:03 ERROR billing timeout\n",
        "2026-03-02T08:00:04 WARNING cache miss\n",
    ]

    summary = analyse_lines(lines)

    assert summary.counts_by_level == {"DEBUG": 0, "INFO": 1, "WARNING": 1, "ERROR": 3}
    assert summary.top_errors == [("db connection refused", 2), ("billing timeout", 1)]


def test_analyse_lines_limits_top_errors() -> None:
    lines = [f"2026-03-02T08:00:0{n} ERROR api failure {n}\n" for n in range(5)]

    summary = analyse_lines(lines, top_n=2)

    assert len(summary.top_errors) == 2


def test_analyse_lines_time_range_ignores_line_order() -> None:
    lines = [
        "2026-03-02T09:00:00 INFO api ok\n",
        "2026-03-02T07:00:00 INFO api ok\n",
        "2026-03-02T08:00:00 INFO api ok\n",
    ]

    summary = analyse_lines(lines)

    assert summary.first_timestamp == datetime(2026, 3, 2, 7, 0, 0)
    assert summary.last_timestamp == datetime(2026, 3, 2, 9, 0, 0)


def test_analyse_lines_reports_bad_lines_without_stopping() -> None:
    lines = [
        "2026-03-02T08:00:00 INFO api ok\n",
        "\x00\x00binary junk\x00\n",
        "Traceback (most recent call last):\n",
        "2026-03-02T08:00:01 INFO api ok\n",
    ]

    summary = analyse_lines(lines)

    assert summary.total_lines == 4
    assert summary.parsed_lines == 2
    assert [bad.line_number for bad in summary.bad_lines] == [2, 3]
    assert summary.bad_lines[0].text == "\x00\x00binary junk\x00"


def test_analyse_lines_with_no_valid_lines_has_no_time_range() -> None:
    summary = analyse_lines(["not a log line\n"])

    assert summary.parsed_lines == 0
    assert summary.first_timestamp is None
    assert summary.last_timestamp is None
    assert summary.to_dict()["time_range"] == {"start": None, "end": None}


def test_analyse_file_on_messy_log() -> None:
    summary = analyse_file(FIXTURE)

    assert summary.total_lines == 472
    assert summary.parsed_lines == 461
    assert len(summary.bad_lines) == 11
    assert summary.counts_by_level == {"DEBUG": 65, "INFO": 299, "WARNING": 58, "ERROR": 39}
    assert summary.top_errors[0] == ("api unhandled exception KeyError: 'customer_id'", 13)
    assert summary.first_timestamp == datetime(2026, 3, 2, 8, 0, 4)
    assert summary.last_timestamp == datetime(2026, 3, 2, 11, 30, 15)


def test_analyse_file_replaces_invalid_utf8(tmp_path: Path) -> None:
    log = tmp_path / "bad_bytes.log"
    log.write_bytes(b"2026-03-02T08:00:00 INFO api caf\xe9\n")

    summary = analyse_file(log)

    assert summary.parsed_lines == 1


def test_analyse_file_missing_raises_log_file_error(tmp_path: Path) -> None:
    with pytest.raises(LogFileError, match="cannot read log file"):
        analyse_file(tmp_path / "missing.log")
