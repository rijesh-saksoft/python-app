from pathlib import Path

import pytest

from app.services.chunking import Chunk
from app.services.vector_store import VectorStore

MEALS = Chunk(doc="expenses.md", index=0, text="meals")
HOTELS = Chunk(doc="travel.md", index=0, text="hotels")
LEAVE = Chunk(doc="leave.md", index=0, text="leave")


def make_store() -> VectorStore:
    store = VectorStore()
    store.add([MEALS, HOTELS, LEAVE], [[1.0, 0.0, 0.0], [0.7, 0.7, 0.0], [0.0, 0.0, 5.0]])
    return store


def test_search_ranks_by_cosine_similarity_and_ignores_length() -> None:
    hits = make_store().search([2.0, 0.1, 0.0], k=3)

    assert [hit.chunk for hit in hits] == [MEALS, HOTELS, LEAVE]
    assert hits[0].score == pytest.approx(0.9988, abs=1e-4)


def test_search_returns_at_most_k_hits() -> None:
    assert len(make_store().search([1.0, 0.0, 0.0], k=2)) == 2


def test_add_refuses_a_vector_count_that_does_not_match_the_chunks() -> None:
    with pytest.raises(ValueError, match="vectors"):
        VectorStore().add([MEALS, HOTELS], [[1.0, 0.0]])


def test_saved_store_loads_with_the_same_results(tmp_path: Path) -> None:
    path = tmp_path / "store.json"
    make_store().save(path)

    hits = VectorStore.load(path).search([0.0, 0.0, 1.0], k=1)

    assert hits[0].chunk == LEAVE
