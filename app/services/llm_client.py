"""The one module that calls language models (Playbook AI-01, AI-02).

It speaks the OpenAI-compatible chat and embeddings APIs, which hosted providers and Ollama
both accept, so switching provider is a settings change. Each model gets retries for 5xx,
429 and network errors; when a chat model stays unavailable, the next model in the fallback
list is tried.
Errors in our own request (bad key, bad input) are not retried and do not fall back: every
other model would reject them too. Prompts and replies are never logged: they can hold
personal data.
"""

import logging
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator

from app.config import Settings
from app.services.http_retry import RetryPolicy, is_retryable, send_with_retries

logger = logging.getLogger(__name__)

NOT_FOUND = 404

Message = Mapping[str, object]


class LlmError(Exception):
    """Base class for every error the LLM client raises."""


class LlmConfigError(LlmError):
    """The settings are missing a value the client needs."""


class LlmUnavailableError(LlmError):
    """No model could answer: network errors, 5xx, 429 or an unknown model, after retries."""


class LlmRequestError(LlmError):
    """The provider rejected our request (bad key, bad input). Retrying will not help."""

    def __init__(self, model: str, status_code: int) -> None:
        super().__init__(f"model {model} rejected the request with HTTP {status_code}")
        self.status_code = status_code


class LlmResponseError(LlmError):
    """The provider answered, but not in the chat-completion shape."""


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    usage: TokenUsage | None  # None when the provider does not report usage
    finish_reason: str | None  # "length" means the answer was cut at max_tokens
    latency_seconds: float


class _Usage(BaseModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


class _ReplyMessage(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _ReplyMessage
    finish_reason: str | None = None

    @model_validator(mode="after")
    def _text_missing_only_when_cut(self) -> Self:
        # A reply cut before any text (thinking used max_tokens) has no content; any other
        # reply without text is malformed.
        if self.message.content is None and self.finish_reason != "length":
            raise ValueError("reply has no text")
        return self


class _ChatReply(BaseModel):
    model: str | None = None
    choices: list[_Choice] = Field(min_length=1)
    usage: _Usage | None = None


class _Embedding(BaseModel):
    index: int = Field(ge=0)
    embedding: list[float] = Field(min_length=1)


class _EmbeddingReply(BaseModel):
    data: list[_Embedding]


def _http_client(
    base_url: str, api_key: SecretStr, timeout: float, transport: httpx.BaseTransport | None
) -> httpx.Client:
    key = api_key.get_secret_value()
    # Local servers such as Ollama need no key; never send an empty bearer token.
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return httpx.Client(
        base_url=base_url, headers=headers, timeout=httpx.Timeout(timeout), transport=transport
    )


def _post(
    http: httpx.Client,
    path: str,
    body: Mapping[str, object],
    *,
    model: str,
    retry: RetryPolicy,
    sleep: Callable[[float], None],
    rng: random.Random,
) -> httpx.Response:
    """Send with retries, and turn every failure into one of this module's errors."""
    try:
        response = send_with_retries(
            lambda: http.post(path, json=body),
            policy=retry,
            sleep=sleep,
            rng=rng,
            label=f"model {model}",
        )
    except httpx.TransportError as exc:
        raise LlmUnavailableError(f"{type(exc).__name__}") from exc
    if response.status_code == NOT_FOUND or is_retryable(response.status_code):
        raise LlmUnavailableError(f"HTTP {response.status_code}")
    if not response.is_success:
        raise LlmRequestError(model, response.status_code)
    return response


class LlmClient:
    def __init__(
        self,
        base_url: str,
        *,
        models: Sequence[str],
        api_key: SecretStr,
        timeout: float,
        max_output_tokens: int = 1024,
        temperature: float = 0.0,
        reasoning_effort: str = "",
        retry: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._http = _http_client(base_url, api_key, timeout, transport)
        self.models = tuple(models)
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        # Jitter only spreads retries out; it is not a security value.
        self._rng = rng or random.Random()  # noqa: S311  # nosec B311
        self.total_usage = TokenUsage()

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if not settings.llm_base_url:
            raise LlmConfigError("LLM_BASE_URL is not set")
        if not settings.llm_model:
            raise LlmConfigError("LLM_MODEL is not set")
        return cls(
            settings.llm_base_url,
            models=[settings.llm_model, *settings.llm_fallback_models],
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            max_output_tokens=settings.llm_max_output_tokens,
            temperature=settings.llm_temperature,
            reasoning_effort=settings.llm_reasoning_effort,
            retry=RetryPolicy(max_attempts=settings.llm_max_attempts),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        seed: int | None = None,
        json_output: bool = False,
    ) -> Completion:
        """Send a chat request to the first model that can answer it."""
        payload: dict[str, object] = {
            "messages": list(messages),
            "temperature": self._temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self._max_output_tokens,
        }
        if seed is not None:
            payload["seed"] = seed
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort

        for model in self.models:
            try:
                return self._complete_with(model, payload)
            except LlmUnavailableError as exc:
                logger.warning("model %s unavailable: %s", model, exc)
        raise LlmUnavailableError(f"no model answered: {', '.join(self.models)}")

    def _complete_with(self, model: str, payload: Mapping[str, object]) -> Completion:
        started = time.perf_counter()
        response = _post(
            self._http,
            "chat/completions",
            {**payload, "model": model},
            model=model,
            retry=self._retry,
            sleep=self._sleep,
            rng=self._rng,
        )
        reply = self._parse(response, model)
        completion = Completion(
            text=reply.choices[0].message.content or "",
            model=reply.model or model,
            usage=TokenUsage(reply.usage.prompt_tokens, reply.usage.completion_tokens)
            if reply.usage
            else None,
            finish_reason=reply.choices[0].finish_reason,
            latency_seconds=time.perf_counter() - started,
        )
        self._record(completion)
        return completion

    @staticmethod
    def _parse(response: httpx.Response, model: str) -> _ChatReply:
        try:
            return _ChatReply.model_validate_json(response.content)
        except ValidationError as exc:
            fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
            raise LlmResponseError(f"model {model} sent an unexpected reply ({fields})") from exc

    def _record(self, completion: Completion) -> None:
        if completion.usage:
            self.total_usage += completion.usage
        logger.info(
            "model %s answered in %.2fs, tokens in=%s out=%s, finish=%s",
            completion.model,
            completion.latency_seconds,
            completion.usage.prompt_tokens if completion.usage else "?",
            completion.usage.completion_tokens if completion.usage else "?",
            completion.finish_reason,
        )
        if completion.finish_reason == "length":
            logger.warning("model %s stopped at max_tokens; the answer is cut", completion.model)


class EmbeddingClient:
    """Turns texts into vectors. One model and no fallback: vectors from another model live
    in a different space and cannot be compared with the stored ones."""

    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        api_key: SecretStr,
        timeout: float,
        batch_size: int = 32,
        query_prefix: str = "",
        document_prefix: str = "",
        retry: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._http = _http_client(base_url, api_key, timeout, transport)
        self.model = model
        self._batch_size = batch_size
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        # Jitter only spreads retries out; it is not a security value.
        self._rng = rng or random.Random()  # noqa: S311  # nosec B311

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        if not settings.embedding_base_url:
            raise LlmConfigError("EMBEDDING_BASE_URL is not set")
        if not settings.embedding_model:
            raise LlmConfigError("EMBEDDING_MODEL is not set")
        return cls(
            settings.embedding_base_url,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            timeout=settings.embedding_timeout_seconds,
            query_prefix=settings.embedding_query_prefix,
            document_prefix=settings.embedding_document_prefix,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [self._document_prefix + text for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(prefixed), self._batch_size):
            vectors += self._embed(prefixed[start : start + self._batch_size])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self._query_prefix + text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        response = _post(
            self._http,
            "embeddings",
            {"model": self.model, "input": texts},
            model=self.model,
            retry=self._retry,
            sleep=self._sleep,
            rng=self._rng,
        )
        try:
            reply = _EmbeddingReply.model_validate_json(response.content)
        except ValidationError as exc:
            raise LlmResponseError(f"model {self.model} sent an unexpected reply") from exc
        # The API marks each vector with the position of its input; it need not keep order.
        vectors = {item.index: item.embedding for item in reply.data}
        if sorted(vectors) != list(range(len(texts))):
            raise LlmResponseError(
                f"model {self.model} returned {len(vectors)} vectors for {len(texts)} texts"
            )
        return [vectors[i] for i in range(len(texts))]
