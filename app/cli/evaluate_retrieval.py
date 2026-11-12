"""Command line: compare the three chunking strategies by top-k retrieval on the labelled
policy questions, and save the per-question results.

The embedding model comes from settings. For the local model, override them for one command:
    EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1/ EMBEDDING_MODEL=nomic-embed-text \
    EMBEDDING_QUERY_PREFIX="search_query: " EMBEDDING_DOCUMENT_PREFIX="search_document: " \
    uv run python -m app.cli.evaluate_retrieval
"""

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from app.config import get_settings
from app.logging_config import setup_logging
from app.services.llm_client import EmbeddingClient, LlmError
from app.services.rag_evaluation import (
    QuestionFileError,
    format_ranks,
    format_table,
    load_questions,
    run_all,
)

logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).resolve().parents[2] / "evals" / "rag"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare chunking strategies by retrieval.")
    parser.add_argument("--docs-dir", type=Path, default=RAG_DIR / "docs")
    parser.add_argument("--questions", type=Path, default=RAG_DIR / "questions.json")
    parser.add_argument("--output", type=Path, help="Result file (default: results/<model>.json)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging()
    docs = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(args.docs_dir.glob("*.md"))
    }
    try:
        questions = load_questions(args.questions, set(docs))
    except QuestionFileError as exc:
        logger.error("%s", exc)
        return 1

    settings = get_settings()
    try:
        with EmbeddingClient.from_settings(settings) as embedder:
            results = run_all(docs, questions, embedder)
    except LlmError as exc:
        logger.error("%s", exc)
        return 1

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", settings.embedding_model)
    output: Path = args.output or RAG_DIR / "results" / f"{safe_name}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([asdict(r) for r in results], indent=2) + "\n", encoding="utf-8")
    logger.info("results saved to %s", output)
    sys.stdout.write(f"{format_table(results)}\n\n{format_ranks(results)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
