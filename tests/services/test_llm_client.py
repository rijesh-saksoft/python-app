import json
import random
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.http_retry import RetryPolicy
from app.services.llm_client import (
    LlmClient,
    LlmConfigError,
    LlmRequestError,
    LlmResponseError,
    LlmUnavailableError,
)

BASE_URL = "http://llm.test/v1/"
FAKE_KEY = "fake-key-for-tests"
MESSAGES = [{"role": "user", "content": "Say hi"}]
Handler = Callable[[httpx.Request], httpx.Response]


def completion(
    text: str = "hi", model: str = "model-a", prompt: int = 12, output: int = 3
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [
                {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": prompt, "completion_tokens": output},
        },
    )


def sequence(*responses: httpx.Response | Exception) -> tuple[Handler, list[httpx.Request]]:
    """Return the responses in order and record every request made."""
    queue = list(responses)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return handle, seen


def body(request: httpx.Request) -> dict[str, object]:
    return json.loads(request.content)


def make_client(
    handler: Handler,
    models: tuple[str, ...] = ("model-a",),
    api_key: str = FAKE_KEY,
    sleeps: list[float] | None = None,
) -> LlmClient:
    return LlmClient(
        BASE_URL,
        models=models,
        api_key=SecretStr(api_key),
        timeout=20.0,
        retry=RetryPolicy(max_attempts=2, base_delay=1.0, max_delay=30.0),
        transport=httpx.MockTransport(handler),
        sleep=(sleeps if sleeps is not None else []).append,
        rng=random.Random(0),
    )


def test_sends_openai_compatible_request() -> None:
    handler, seen = sequence(completion())

    with make_client(handler) as client:
        client.complete(MESSAGES, temperature=0.0, max_tokens=50)

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}chat/completions"
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert request.extensions["timeout"] == httpx.Timeout(20.0).as_dict()
    sent = body(request)
    assert sent["model"] == "model-a"
    assert sent["messages"] == MESSAGES
    assert sent["temperature"] == 0.0
    assert sent["max_tokens"] == 50


def test_no_authorization_header_without_key() -> None:
    handler, seen = sequence(completion())

    with make_client(handler, api_key="") as client:
        client.complete(MESSAGES)

    assert "Authorization" not in seen[0].headers


def test_optional_fields_sent_only_when_asked() -> None:
    handler, seen = sequence(completion(), completion())

    with make_client(handler) as client:
        client.complete(MESSAGES)
        client.complete(MESSAGES, seed=42, json_output=True)

    assert "seed" not in body(seen[0])
    assert "response_format" not in body(seen[0])
    assert body(seen[1])["seed"] == 42
    assert body(seen[1])["response_format"] == {"type": "json_object"}


def test_reasoning_effort_sent_only_when_configured() -> None:
    handler, seen = sequence(completion(), completion())

    with make_client(handler) as client:
        client.complete(MESSAGES)
    with LlmClient(
        BASE_URL,
        models=["model-a"],
        api_key=SecretStr(""),
        timeout=20.0,
        reasoning_effort="none",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.complete(MESSAGES)

    assert "reasoning_effort" not in body(seen[0])
    assert body(seen[1])["reasoning_effort"] == "none"


def test_returns_text_model_and_token_counts() -> None:
    handler, _ = sequence(completion("hello", prompt=100, output=7))

    with make_client(handler) as client:
        result = client.complete(MESSAGES)

    assert result.text == "hello"
    assert result.model == "model-a"
    assert result.finish_reason == "stop"
    assert result.usage is not None
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (100, 7)
    assert result.usage.total_tokens == 107


def test_counts_tokens_across_calls() -> None:
    handler, _ = sequence(completion(prompt=10, output=2), completion(prompt=20, output=5))

    with make_client(handler) as client:
        client.complete(MESSAGES)
        client.complete(MESSAGES)

        assert client.total_usage.prompt_tokens == 30
        assert client.total_usage.completion_tokens == 7


def test_missing_usage_is_reported_as_none() -> None:
    reply = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    handler, _ = sequence(httpx.Response(200, json=reply))

    with make_client(handler) as client:
        result = client.complete(MESSAGES)

    assert result.usage is None
    assert result.model == "model-a"


def test_retries_5xx_then_succeeds() -> None:
    sleeps: list[float] = []
    handler, seen = sequence(httpx.Response(503), completion())

    with make_client(handler, sleeps=sleeps) as client:
        result = client.complete(MESSAGES)

    assert result.text == "hi"
    assert len(seen) == 2
    assert len(sleeps) == 1


def test_429_respects_retry_after() -> None:
    sleeps: list[float] = []
    handler, _ = sequence(httpx.Response(429, headers={"Retry-After": "4"}), completion())

    with make_client(handler, sleeps=sleeps) as client:
        client.complete(MESSAGES)

    assert sleeps == [4.0]


def test_falls_back_to_next_model_after_retries() -> None:
    handler, seen = sequence(httpx.Response(503), httpx.Response(503), completion(model="model-b"))

    with make_client(handler, models=("model-a", "model-b")) as client:
        result = client.complete(MESSAGES)

    assert [body(request)["model"] for request in seen] == ["model-a", "model-a", "model-b"]
    assert result.model == "model-b"


def test_falls_back_at_once_when_model_not_found() -> None:
    handler, seen = sequence(httpx.Response(404), completion(model="model-b"))

    with make_client(handler, models=("model-a", "model-b")) as client:
        result = client.complete(MESSAGES)

    assert [body(request)["model"] for request in seen] == ["model-a", "model-b"]
    assert result.model == "model-b"


def test_falls_back_after_timeouts() -> None:
    handler, _ = sequence(
        httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"), completion(model="model-b")
    )

    with make_client(handler, models=("model-a", "model-b")) as client:
        result = client.complete(MESSAGES)

    assert result.model == "model-b"


def test_bad_key_does_not_fall_back() -> None:
    handler, seen = sequence(httpx.Response(401))

    with (
        make_client(handler, models=("model-a", "model-b")) as client,
        pytest.raises(LlmRequestError) as error,
    ):
        client.complete(MESSAGES)

    assert error.value.status_code == 401
    assert len(seen) == 1


def test_all_models_failing_raises_unavailable() -> None:
    handler, seen = sequence(*(httpx.Response(500) for _ in range(4)))

    with (
        make_client(handler, models=("model-a", "model-b")) as client,
        pytest.raises(LlmUnavailableError, match="model-a, model-b"),
    ):
        client.complete(MESSAGES)

    assert len(seen) == 4


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>proxy error</html>"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    ],
)
def test_malformed_reply_raises_response_error(response: httpx.Response) -> None:
    handler, _ = sequence(response)

    with make_client(handler) as client, pytest.raises(LlmResponseError):
        client.complete(MESSAGES)


def test_errors_never_show_the_key_or_the_reply_body() -> None:
    handler, _ = sequence(httpx.Response(400, json={"error": "private-provider-detail"}))

    with make_client(handler) as client, pytest.raises(LlmRequestError) as error:
        client.complete(MESSAGES)

    assert FAKE_KEY not in str(error.value)
    assert "private-provider-detail" not in str(error.value)


def test_from_settings_uses_primary_then_fallback_models() -> None:
    settings = Settings(
        llm_base_url=BASE_URL,
        llm_model="model-a",
        llm_fallback_models=["model-b", "model-c"],
        llm_api_key=SecretStr(FAKE_KEY),
    )

    with LlmClient.from_settings(settings) as client:
        assert client.models == ("model-a", "model-b", "model-c")


@pytest.mark.parametrize(
    ("settings", "missing"),
    [
        (Settings(llm_base_url="", llm_model="model-a"), "LLM_BASE_URL"),
        (Settings(llm_base_url=BASE_URL, llm_model=""), "LLM_MODEL"),
    ],
)
def test_from_settings_requires_base_url_and_model(settings: Settings, missing: str) -> None:
    with pytest.raises(LlmConfigError, match=missing):
        LlmClient.from_settings(settings)
