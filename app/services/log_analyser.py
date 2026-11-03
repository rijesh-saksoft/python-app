import logging
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from app.models.log_entry import BadLine, LogEntry, LogSummary

logger = logging.getLogger(__name__)

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"
MAX_BAD_LINE_TEXT = 200


class LogAnalyserError(Exception):
    """Base class for every error the log analyser raises."""


class LogFileError(LogAnalyserError):
    """The log file cannot be opened or read."""


class LogLineError(LogAnalyserError):
    """A line does not follow `TIMESTAMP LEVEL MODULE MESSAGE`."""


def parse_line(text: str) -> LogEntry:
    """Parse one line, or raise LogLineError saying why it is broken."""
    if not text.strip():
        raise LogLineError("blank line")
    fields = text.split(maxsplit=3)
    if len(fields) != 4:
        raise LogLineError("wrong number of fields")
    raw_timestamp, level, module, message = fields
    try:
        timestamp = datetime.strptime(raw_timestamp, TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise LogLineError("invalid timestamp") from exc
    if level not in LEVELS:
        raise LogLineError("unknown level")
    return LogEntry(timestamp=timestamp, level=level, module=module, message=message)


def analyse_lines(lines: Iterable[str], top_n: int = 5) -> LogSummary:
    counts_by_level: dict[str, int] = dict.fromkeys(LEVELS, 0)
    error_counts: Counter[str] = Counter()
    timestamps: list[datetime] = []
    bad_lines: list[BadLine] = []
    total_lines = 0

    for total_lines, raw in enumerate(lines, start=1):
        text = raw.rstrip("\r\n")
        try:
            entry = parse_line(text)
        except LogLineError as exc:
            bad_lines.append(BadLine(total_lines, str(exc), text[:MAX_BAD_LINE_TEXT]))
            logger.debug("bad line %d: %s", total_lines, exc)
            continue
        counts_by_level[entry.level] += 1
        timestamps.append(entry.timestamp)
        if entry.level == "ERROR":
            error_counts[f"{entry.module} {entry.message}"] += 1

    if bad_lines:
        logger.warning("skipped %d bad lines of %d", len(bad_lines), total_lines)
    return LogSummary(
        total_lines=total_lines,
        counts_by_level=counts_by_level,
        top_errors=error_counts.most_common(top_n),
        first_timestamp=min(timestamps, default=None),
        last_timestamp=max(timestamps, default=None),
        bad_lines=bad_lines,
    )


def analyse_file(path: Path, top_n: int = 5) -> LogSummary:
    """Summarise a log file. Bytes that are not UTF-8 are replaced, not fatal."""
    logger.info("analysing %s", path)
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            return analyse_lines(handle, top_n)
    except OSError as exc:
        raise LogFileError(f"cannot read log file {path}: {exc.strerror}") from exc
