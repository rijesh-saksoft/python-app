"""Compare chunking strategies by retrieval: for each labelled question, at which position
does the first chunk from an expected document appear?

hit@k counts the questions whose expected document is among the top k chunks: the chunks a
model would be given to answer from. MRR (mean reciprocal rank) also rewards finding it
higher up: 1 for first place, 1/2 for second, 0 when it is not in the top K_MAX.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from app.services.chunking import Chunk, by_section, by_sentences, fixed_size
from app.services.vector_store import VectorStore

K_MAX = 5
REPORTED_K = (1, 3, 5)

Chunker = Callable[[str, str], list[Chunk]]
STRATEGIES: dict[str, Chunker] = {
    "fixed_size": fixed_size,
    "by_section": by_section,
    "by_sentences": by_sentences,
}


class QuestionFileError(Exception):
    """The questions file is missing labels or names documents that do not exist."""


class Question(BaseModel):
    id: str
    question: str = Field(min_length=1)
    expected_docs: list[str]


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class QuestionResult:
    id: str
    expected_docs: list[str]
    top_docs: list[str]  # the document of each of the top K_MAX chunks, best first
    rank: int | None  # 1-based position of the first expected chunk; None if not found


@dataclass(frozen=True, slots=True)
class StrategyResult:
    strategy: str
    chunk_count: int
    average_chars: float
    results: list[QuestionResult] = field(default_factory=list)

    def hits_at(self, k: int) -> int:
        return sum(1 for r in self.results if r.rank is not None and r.rank <= k)

    @property
    def mrr(self) -> float:
        return sum(1 / r.rank for r in self.results if r.rank) / len(self.results)


def load_questions(path: Path, known_docs: set[str]) -> list[Question]:
    try:
        questions = TypeAdapter(list[Question]).validate_json(path.read_bytes())
    except ValidationError as exc:
        raise QuestionFileError(f"{path} is not a valid questions file") from exc
    unlabelled = [q.id for q in questions if not q.expected_docs]
    if unlabelled:
        raise QuestionFileError(f"questions without expected_docs: {', '.join(unlabelled)}")
    unknown = sorted({doc for q in questions for doc in q.expected_docs} - known_docs)
    if unknown:
        raise QuestionFileError(f"expected_docs names unknown documents: {', '.join(unknown)}")
    return questions


def run_all(
    docs: Mapping[str, str],
    questions: Sequence[Question],
    embedder: Embedder,
    strategies: Mapping[str, Chunker] = STRATEGIES,
) -> list[StrategyResult]:
    query_vectors = [embedder.embed_query(q.question) for q in questions]
    results = []
    for name, chunker in strategies.items():
        chunks = [chunk for doc, text in docs.items() for chunk in chunker(doc, text)]
        store = VectorStore()
        store.add(chunks, embedder.embed_documents([chunk.text for chunk in chunks]))
        results.append(
            StrategyResult(
                strategy=name,
                chunk_count=len(chunks),
                average_chars=sum(len(c.text) for c in chunks) / len(chunks),
                results=[
                    _score(question, store, vector)
                    for question, vector in zip(questions, query_vectors, strict=True)
                ],
            )
        )
    return results


def _score(question: Question, store: VectorStore, vector: list[float]) -> QuestionResult:
    top_docs = [hit.chunk.doc for hit in store.search(vector, k=K_MAX)]
    rank = next(
        (i for i, doc in enumerate(top_docs, start=1) if doc in question.expected_docs), None
    )
    return QuestionResult(question.id, question.expected_docs, top_docs, rank)


def format_table(results: Sequence[StrategyResult]) -> str:
    k_headers = " | ".join(f"hit@{k}" for k in REPORTED_K)
    lines = [
        f"| Chunking | Chunks | Average characters | {k_headers} | MRR |",
        "| --- " * (4 + len(REPORTED_K)) + "|",
    ]
    for r in results:
        total = len(r.results)
        hits = " | ".join(f"{r.hits_at(k)}/{total}" for k in REPORTED_K)
        lines.append(
            f"| {r.strategy} | {r.chunk_count} | {r.average_chars:.0f} | {hits} | {r.mrr:.2f} |"
        )
    return "\n".join(lines)


def format_ranks(results: Sequence[StrategyResult]) -> str:
    """Per question: the rank in each strategy, or what came first when it was missed."""
    lines = [
        "| Question | Expected | " + " | ".join(r.strategy for r in results) + " |",
        "| --- " * (2 + len(results)) + "|",
    ]
    for i, first in enumerate(results[0].results):
        cells = []
        for r in results:
            result = r.results[i]
            cells.append(str(result.rank) if result.rank else f"miss ({result.top_docs[0]})")
        lines.append(f"| {first.id} | {', '.join(first.expected_docs)} | {' | '.join(cells)} |")
    return "\n".join(lines)
