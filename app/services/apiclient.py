import logging
import random
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Self

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.models.parcels import ApiMeta, OffsetPage, Record

logger = logging.getLogger(__name__)

TOO_MANY_REQUESTS = 429


class ApiClientError(Exception):
    """Base class for every error the API client raises."""


class ApiConnectionError(ApiClientError):
    """The server could not be reached, or did not answer in time, after all retries."""


class ApiStatusError(ApiClientError):
    def __init__(self, method: str, path: str, status_code: int) -> None:
        super().__init__(f"{method} {path} failed with HTTP {status_code}")
        self.status_code = status_code


class ApiResponseError(ApiClientError):
    """The server answered, but not with the shape we expect."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 30.0

    def backoff(self, attempt: int, rng: random.Random) -> float:
        """Full jitter: a random wait between 0 and the capped exponential delay."""
        return rng.uniform(0, min(self.max_delay, self.base_delay * 2**attempt))


def _is_retryable(status_code: int) -> bool:
    return status_code == TOO_MANY_REQUESTS or status_code >= 500


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Read Retry-After, which is either a number of seconds or an HTTP date."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        retry: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url, timeout=httpx.Timeout(timeout), transport=transport
        )
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        # Jitter only spreads retries out; it is not a security value.
        self._rng = rng or random.Random()  # noqa: S311  # nosec B311

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            settings.parcels_api_base_url,
            timeout=settings.parcels_api_timeout_seconds,
            retry=RetryPolicy(max_attempts=settings.parcels_api_max_attempts),
        )

    @property
    def base_url(self) -> httpx.URL:
        return self._http.base_url

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

    def get_meta(self) -> ApiMeta:
        return self._validate(ApiMeta, self.get_json("/v1/meta"), "/v1/meta")

    def paginate[T: Record](self, path: str, model: type[T], page_size: int = 100) -> Iterator[T]:
        """Yield every record, page by page, each one validated.

        Offset paging can repeat a record at a page edge (the mock API does, and any API
        does when rows are inserted while we page), so ids already seen are skipped.
        """
        seen: set[int] = set()
        offset = 0
        while True:
            params = {"offset": offset, "limit": page_size}
            page = self._validate(OffsetPage, self.get_json(path, params), path)
            for index, item in enumerate(page.items):
                record = self._validate(model, item, f"{path} record {index}")
                if record.id in seen:
                    logger.warning("skipped duplicate id %d from %s", record.id, path)
                    continue
                seen.add(record.id)
                yield record
            offset += len(page.items)
            if not page.items or offset >= page.total:
                return

    def get_json(self, path: str, params: Mapping[str, int | str] | None = None) -> object:
        response = self._send("GET", path, params)
        try:
            return response.json()
        except ValueError as exc:
            raise ApiResponseError(f"GET {path} returned a body that is not JSON") from exc

    def _send(
        self, method: str, path: str, params: Mapping[str, int | str] | None
    ) -> httpx.Response:
        for attempt in range(self._retry.max_attempts):
            last_attempt = attempt == self._retry.max_attempts - 1
            try:
                response = self._http.request(method, path, params=params)
            except httpx.TransportError as exc:
                if last_attempt:
                    raise ApiConnectionError(f"{method} {path} failed: {exc!r}") from exc
                self._wait(attempt, None, f"{type(exc).__name__}", path)
                continue
            if response.is_success:
                return response
            if last_attempt or not _is_retryable(response.status_code):
                raise ApiStatusError(method, path, response.status_code)
            if not self._wait(attempt, response, f"HTTP {response.status_code}", path):
                raise ApiStatusError(method, path, response.status_code)
        raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover

    def _wait(self, attempt: int, response: httpx.Response | None, reason: str, path: str) -> bool:
        """Sleep before the next try. Return False when the server asks for too long a wait."""
        retry_after = _retry_after_seconds(response) if response is not None else None
        if retry_after is not None and retry_after > self._retry.max_delay:
            logger.warning("%s on %s: Retry-After %.0fs is too long", reason, path, retry_after)
            return False
        delay = retry_after if retry_after is not None else self._retry.backoff(attempt, self._rng)
        logger.warning("%s on %s, retry %d in %.2fs", reason, path, attempt + 1, delay)
        self._sleep(delay)
        return True

    @staticmethod
    def _validate[M: BaseModel](model: type[M], data: object, where: str) -> M:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
            raise ApiResponseError(f"{where}: invalid {model.__name__} ({fields})") from exc
