import json

import httpx
import pytest
from pydantic import SecretStr

from app.services.llm_client import LlmClient
from app.services.token_count import TokenCount, TokenCountError, count_tokens, format_table

TEMPLATE_TOKENS = 8
TOKENS_PER_WORD = {".": 1, "hello world": 2, "a much longer text": 5}


def usage_reply(request: httpx.Request) -> httpx.Response:
    text = json.loads(request.content)["messages"][0]["content"]
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "x"}, "finish_reason": "length"}],
            "usage": {
                "prompt_tokens": TEMPLATE_TOKENS + TOKENS_PER_WORD[text],
                "completion_tokens": 1,
            },
        },
    )


def no_usage_reply(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})


def make_client(handler: object) -> LlmClient:
    return LlmClient(
        "http://llm.test/v1/",
        models=["model-a"],
        api_key=SecretStr(""),
        timeout=5,
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


def test_count_takes_the_chat_template_off_every_text() -> None:
    with make_client(usage_reply) as llm:
        counts = count_tokens(llm, {"short": "hello world", "long": "a much longer text"})

    assert [(c.name, c.tokens) for c in counts] == [("short", 2), ("long", 5)]


def test_count_refuses_a_provider_that_reports_no_usage() -> None:
    with make_client(no_usage_reply) as llm, pytest.raises(TokenCountError, match="usage"):
        count_tokens(llm, {"short": "hello world"})


def test_table_shows_characters_per_token() -> None:
    table = format_table([TokenCount(name="prose", text="hello world", tokens=2)])

    assert "| prose | 11 | 2 | 2 | 5.5 |" in table
