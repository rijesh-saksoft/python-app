import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.http_retry import RetryPolicy
from app.services.llm_client import (
    EmbeddingClient,
    LlmConfigError,
    LlmRequestError,
    LlmResponseError,
    LlmUnavailableError,
)


def vectors_for(request: httpx.Request) -> httpx.Response:
    texts = json.loads(request.content)["input"]
    # Reversed on purpose: the API marks each vector with the index of its input.
    data = [{"index": i, "embedding": [float(len(t)), 1.0]} for i, t in enumerate(texts)]
    return httpx.Response(200, json={"data": data[::-1]})


def make_client(handler: object, batch_size: int = 32) -> tuple[EmbeddingClient, list[dict]]:
    seen: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return handler(request)  # type: ignore[operator]

    client = EmbeddingClient(
        "http://llm.test/v1/",
        model="embed-model",
        api_key=SecretStr(""),
        timeout=5,
        batch_size=batch_size,
        query_prefix="q: ",
        document_prefix="d: ",
        retry=RetryPolicy(max_attempts=1),
        transport=httpx.MockTransport(record),
    )
    return client, seen


def test_documents_get_their_prefix_and_keep_their_order_across_batches() -> None:
    client, seen = make_client(vectors_for, batch_size=2)

    with client:
        vectors = client.embed_documents(["a", "bb", "ccc"])

    assert [body["input"] for body in seen] == [["d: a", "d: bb"], ["d: ccc"]]
    assert [vector[0] for vector in vectors] == [4.0, 5.0, 6.0]
    assert seen[0]["model"] == "embed-model"


def test_query_gets_the_query_prefix() -> None:
    client, seen = make_client(vectors_for)

    with client:
        vector = client.embed_query("abc")

    assert seen[0]["input"] == ["q: abc"]
    assert vector == [6.0, 1.0]


def test_missing_vector_is_a_response_error() -> None:
    client, _ = make_client(lambda _: httpx.Response(200, json={"data": []}))

    with client, pytest.raises(LlmResponseError, match="1 texts"):
        client.embed_documents(["a"])


@pytest.mark.parametrize(
    ("status", "error"),
    [(503, LlmUnavailableError), (404, LlmUnavailableError), (400, LlmRequestError)],
)
def test_http_errors_map_like_the_chat_client(status: int, error: type[Exception]) -> None:
    client, _ = make_client(lambda _: httpx.Response(status))

    with client, pytest.raises(error):
        client.embed_query("abc")


def test_settings_without_a_model_are_refused() -> None:
    with pytest.raises(LlmConfigError, match="EMBEDDING_MODEL"):
        EmbeddingClient.from_settings(Settings(embedding_base_url="http://llm.test/v1/"))
