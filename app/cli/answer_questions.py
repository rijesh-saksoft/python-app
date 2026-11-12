"""Command line: answer the labelled policy questions with retrieval. Section chunks are
embedded, the top k are retrieved per question, and the chat model answers from them only.

Chat and embedding models come from settings, e.g. the local embedding model with the
configured chat model:
    EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1/ EMBEDDING_MODEL=nomic-embed-text \
    EMBEDDING_QUERY_PREFIX="search_query: " EMBEDDING_DOCUMENT_PREFIX="search_document: " \
    uv run python -m app.cli.answer_questions
"""

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.logging_config import setup_logging
from app.services.answering import answer_from_passages
from app.services.chunking import by_section
from app.services.llm_client import EmbeddingClient, LlmClient, LlmError
from app.services.rag_evaluation import QuestionFileError, load_questions
from app.services.structured_output import StructuredOutputError
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

RAG_DIR = Path(__file__).resolve().parents[2] / "evals" / "rag"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Answer the policy questions with retrieval.")
    parser.add_argument("--docs-dir", type=Path, default=RAG_DIR / "docs")
    parser.add_argument("--questions", type=Path, default=RAG_DIR / "questions.json")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--prompt-version", default="v2")
    parser.add_argument(
        "--output", type=Path, help="Answer file (default: answers/<model>_<prompt version>.json)"
    )
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
    rows = []
    try:
        with (
            EmbeddingClient.from_settings(settings) as embedder,
            LlmClient.from_settings(settings) as llm,
        ):
            chunks = [chunk for doc, text in docs.items() for chunk in by_section(doc, text)]
            store = VectorStore()
            store.add(chunks, embedder.embed_documents([chunk.text for chunk in chunks]))
            for question in questions:
                hits = store.search(embedder.embed_query(question.question), k=args.top_k)
                response = answer_from_passages(
                    llm, question.question, [hit.chunk for hit in hits], args.prompt_version
                )
                rows.append(
                    {
                        "id": question.id,
                        "prompt": f"grounded_answer/{args.prompt_version}",
                        "question": question.question,
                        "expected_docs": question.expected_docs,
                        "retrieved_docs": [hit.chunk.doc for hit in hits],
                        "answer": response.answer,
                        "cited_docs": [citation.source for citation in response.citations],
                    }
                )
    except (LlmError, StructuredOutputError) as exc:
        logger.error("%s", exc)
        return 1

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", settings.llm_model)
    output: Path = args.output or RAG_DIR / "answers" / f"{safe_name}_{args.prompt_version}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("answers saved to %s", output)
    for row in rows:
        sys.stdout.write(f"{row['id']}: {row['answer']}\n    cited: {row['cited_docs']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
