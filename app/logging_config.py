"""JSON logging with a request ID in every line (Playbook LOG-01, LOG-03).

Why JSON?  Tools can search and filter it.  Why a request ID?  So you can follow one
request through every log line when something goes wrong.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# A ContextVar holds a value that belongs to the current request only.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Turn each log record into one JSON object on one line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        # Extra context passed like logger.info("x", extra={"ticket_id": "t_1"})
        for key, value in record.__dict__.get("extra_fields", {}).items():
            entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging(level: int = logging.INFO) -> None:
    """Send JSON logs to standard output (containers collect them from there)."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
