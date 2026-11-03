import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from app.logging_config import setup_logging
from app.services.log_analyser import LogAnalyserError, analyse_file

logger = logging.getLogger(__name__)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarise a log file as JSON.")
    parser.add_argument("file", type=Path, help="Path to the log file")
    parser.add_argument(
        "-n", "--top", type=_positive_int, default=5, help="Number of top errors to report"
    )
    parser.add_argument("-o", "--output", type=Path, help="Write the JSON here, not stdout")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log each bad line")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    try:
        summary = analyse_file(args.file, args.top)
    except LogAnalyserError:
        logger.exception("log analysis failed")
        return 1
    report = json.dumps(summary.to_dict(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
