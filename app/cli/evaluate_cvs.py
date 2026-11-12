"""Command line: run the CV extractor against the gold answers, and build the accuracy table.

The model comes from settings. To evaluate another model, override the settings for one
command, for example the local model:
    LLM_BASE_URL=http://127.0.0.1:11434/v1/ LLM_MODEL=qwen3.5:2b LLM_API_KEY= \
    LLM_REASONING_EFFORT=none uv run python -m app.cli.evaluate_cvs run
"""

import argparse
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.logging_config import setup_logging
from app.models.cv import CandidateProfile
from app.services.cv_evaluation import (
    EvaluationResult,
    GoldFileError,
    format_table,
    load_gold,
    run_evaluation,
    summarise,
)
from app.services.cv_extractor import CvExtractor
from app.services.llm_client import LlmClient, LlmConfigError

logger = logging.getLogger(__name__)

EVALS_DIR = Path(__file__).resolve().parents[2] / "evals" / "cvs"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate CV extraction.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Extract CVs with the configured model and score them")
    run.add_argument("--input-dir", type=Path, default=EVALS_DIR / "input")
    run.add_argument("--gold-dir", type=Path, default=EVALS_DIR / "gold")
    run.add_argument("--output", type=Path, help="Result file (default: results/<model>.json)")
    run.add_argument("--prompt-version", default="v1")
    run.add_argument("--all", action="store_true", help="Also extract CVs without a gold file")

    table = commands.add_parser("table", help="Combine result files into one table")
    table.add_argument("results", type=Path, nargs="+")
    return parser.parse_args(argv)


def _cases(
    input_dir: Path, gold_dir: Path, include_all: bool
) -> list[tuple[str, str, CandidateProfile | None]]:
    cases: list[tuple[str, str, CandidateProfile | None]] = []
    for cv_path in sorted(input_dir.glob("cv_*.txt")):
        gold_path = gold_dir / f"{cv_path.stem}.json"
        if not gold_path.exists() and not include_all:
            continue
        gold = load_gold(gold_path) if gold_path.exists() else None
        cases.append((cv_path.stem, cv_path.read_text(encoding="utf-8"), gold))
    return cases


def _run(args: argparse.Namespace) -> int:
    try:
        cases = _cases(args.input_dir, args.gold_dir, args.all)
    except GoldFileError as exc:
        logger.error("%s", exc)
        return 1
    if not cases:
        logger.error("no CVs to evaluate in %s", args.input_dir)
        return 1

    settings = get_settings()
    try:
        llm = LlmClient.from_settings(settings)
    except LlmConfigError as exc:
        logger.error("%s", exc)
        return 1
    with llm:
        extractor = CvExtractor(llm, args.prompt_version)
        runs = run_evaluation(extractor, cases)

    other_models = {run.model for run in runs if run.model and run.model != settings.llm_model}
    if other_models:
        logger.warning("some CVs were answered by fallback models: %s", sorted(other_models))
    result = EvaluationResult(
        model=settings.llm_model, prompt_version=f"cv_extract/{args.prompt_version}", runs=runs
    )
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", settings.llm_model)
    output: Path = args.output or EVALS_DIR / "results" / f"{safe_name}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    logger.info("results saved to %s", output)
    sys.stdout.write(format_table([summarise(result)]) + "\n")
    return 0


def _table(args: argparse.Namespace) -> int:
    reports = [
        summarise(EvaluationResult.model_validate_json(path.read_text(encoding="utf-8")))
        for path in args.results
    ]
    sys.stdout.write(format_table(reports) + "\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging()
    return _run(args) if args.command == "run" else _table(args)


if __name__ == "__main__":
    sys.exit(main())
