from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime
    level: str
    module: str
    message: str


@dataclass(frozen=True, slots=True)
class BadLine:
    line_number: int
    reason: str
    text: str


@dataclass(frozen=True, slots=True)
class LogSummary:
    total_lines: int
    counts_by_level: dict[str, int]
    top_errors: list[tuple[str, int]]
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    bad_lines: list[BadLine]

    @property
    def parsed_lines(self) -> int:
        return self.total_lines - len(self.bad_lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_lines": self.total_lines,
            "parsed_lines": self.parsed_lines,
            "counts_by_level": self.counts_by_level,
            "top_errors": [
                {"message": message, "count": count} for message, count in self.top_errors
            ],
            "time_range": {
                "start": _isoformat(self.first_timestamp),
                "end": _isoformat(self.last_timestamp),
            },
            "bad_lines": {
                "count": len(self.bad_lines),
                "lines": [
                    {"line_number": bad.line_number, "reason": bad.reason, "text": bad.text}
                    for bad in self.bad_lines
                ],
            },
        }


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
