"""Retry rules shared by every outbound HTTP client.

Only 5xx, 429 and network errors are retried: those can succeed on a later try. Waits use
capped exponential backoff with full jitter, so clients that failed together do not retry
together, and a server's Retry-After is respected.
"""

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

TOO_MANY_REQUESTS = 429


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 0.5
    max_delay: float = 30.0

    def backoff(self, attempt: int, rng: random.Random) -> float:
        """Full jitter: a random wait between 0 and the capped exponential delay."""
        return rng.uniform(0, min(self.max_delay, self.base_delay * 2**attempt))


def is_retryable(status_code: int) -> bool:
    return status_code == TOO_MANY_REQUESTS or status_code >= 500


def retry_after_seconds(response: httpx.Response) -> float | None:
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


def send_with_retries(
    send: Callable[[], httpx.Response],
    *,
    policy: RetryPolicy,
    sleep: Callable[[float], None],
    rng: random.Random,
    label: str,
) -> httpx.Response:
    """Call `send` until it succeeds or a retry cannot help.

    Returns the last response, successful or not, so each client maps error statuses to
    its own exceptions. Re-raises the last httpx.TransportError if no attempt got an answer.
    """
    for attempt in range(policy.max_attempts):
        last_attempt = attempt == policy.max_attempts - 1
        try:
            response = send()
        except httpx.TransportError as exc:
            if last_attempt:
                raise
            delay = policy.backoff(attempt, rng)
            logger.warning(
                "%s on %s, retry %d in %.2fs", type(exc).__name__, label, attempt + 1, delay
            )
            sleep(delay)
            continue
        if response.is_success or last_attempt or not is_retryable(response.status_code):
            return response
        retry_after = retry_after_seconds(response)
        if retry_after is not None and retry_after > policy.max_delay:
            logger.warning(
                "HTTP %d on %s: Retry-After %.0fs is too long",
                response.status_code,
                label,
                retry_after,
            )
            return response
        delay = retry_after if retry_after is not None else policy.backoff(attempt, rng)
        logger.warning(
            "HTTP %d on %s, retry %d in %.2fs", response.status_code, label, attempt + 1, delay
        )
        sleep(delay)
    raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover
