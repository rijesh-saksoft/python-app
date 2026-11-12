"""A simple in-memory vector store: chunks with their embeddings, searched by cosine
similarity. Enough for a few hundred chunks; a database with a vector index replaces it for
real volumes. Vectors are normalised when added, so a search is one dot product per chunk.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services.chunking import Chunk

Vector = Sequence[float]


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float


class VectorStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: list[list[float]] = []

    def add(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        self._chunks.extend(chunks)
        self._vectors.extend(_normalised(vector) for vector in vectors)

    def search(self, query: Vector, k: int) -> list[Hit]:
        unit = _normalised(query)
        hits = [
            Hit(chunk, sum(a * b for a, b in zip(unit, vector, strict=True)))
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
        ]
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:k]

    def save(self, path: Path) -> None:
        rows = [
            {**asdict(chunk), "vector": vector}
            for chunk, vector in zip(self._chunks, self._vectors, strict=True)
        ]
        path.write_text(json.dumps(rows), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> VectorStore:
        store = cls()
        rows = json.loads(path.read_text(encoding="utf-8"))
        store.add(
            [Chunk(doc=row["doc"], index=row["index"], text=row["text"]) for row in rows],
            [row["vector"] for row in rows],
        )
        return store


def _normalised(vector: Vector) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        raise ValueError("cannot compare an all-zero vector")
    return [value / length for value in vector]
