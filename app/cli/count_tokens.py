"""Command line: count the tokens of every text in a folder with the configured model.

To count with the local model, override the settings for one command:
    LLM_BASE_URL=http://127.0.0.1:11434/v1/ LLM_MODEL=qwen3.5:2b LLM_API_KEY= \
    LLM_REASONING_EFFORT=none uv run python -m app.cli.count_tokens
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.logging_config import setup_logging
from app.services.llm_client import LlmClient, LlmConfigError, LlmError
from app.services.token_count import TokenCountError, count_tokens, format_table

logger = logging.getLogger(__name__)

TEXTS_DIR = Path(__file__).resolve().parents[2] / "evals" / "tokens"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Count tokens per text with the configured model."
    )
    parser.add_argument("--input-dir", type=Path, default=TEXTS_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging()
    texts = {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(args.input_dir.glob("*"))
        if path.is_file()
    }
    if not texts:
        logger.error("no texts in %s", args.input_dir)
        return 1

    settings = get_settings()
    try:
        llm = LlmClient.from_settings(settings)
    except LlmConfigError as exc:
        logger.error("%s", exc)
        return 1
    try:
        with llm:
            counts = count_tokens(llm, texts)
    except (LlmError, TokenCountError) as exc:
        logger.error("%s", exc)
        return 1
    sys.stdout.write(f"Model: {settings.llm_model}\n\n{format_table(counts)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
