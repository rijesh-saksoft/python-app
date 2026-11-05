import json
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.config import Settings
from app.models.parcels import Parcel
from app.services.apiclient import (
    ApiClient,
    ApiConnectionError,
    ApiResponseError,
    ApiStatusError,
    RetryPolicy,
)

BASE_URL = "http://api.test"
Handler = Callable[[httpx.Request], httpx.Response]


def parcel(record_id: int, status: str = "active") -> dict[str, object]:
    return {
        "id": record_id,
        "name": f"Birch {record_id:04d}",
        "status": status,
        "category": "alpha",
        "created": "2025-09-08",
    }


def page(ids: list[int], offset: int, total: int) -> httpx.Response:
    items = [parcel(record_id) for record_id in ids]
    return httpx.Response(
        200, json={"items": items, "offset": offset, "limit": len(ids), "total": total}
    )


def offset_server(total: int, quirk: bool = False) -> Handler:
    """Serve ids 1..total by offset; `quirk` copies the real server's 1-based offsets."""

    def handle(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        start = max(offset, 1) if quirk else offset + 1
        ids = list(range(start, min(start + limit, total + 1)))
        return page(ids, offset, total)

    return handle


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


def make_client(
    handler: Handler, sleeps: list[float] | None = None, retry: RetryPolicy | None = None
) -> ApiClient:
    return ApiClient(
        BASE_URL,
        timeout=5.0,
        retry=retry or RetryPolicy(max_attempts=3, base_delay=1.0, max_delay=30.0),
        transport=httpx.MockTransport(handler),
        sleep=(sleeps if sleeps is not None else []).append,
        rng=random.Random(0),
    )


def test_get_meta_validates_response() -> None:
    meta = {"variant": 3, "domain": "Parcels", "entity": "parcels", "pagination": "offset"}
    handler, _ = sequence(httpx.Response(200, json={**meta, "total": 237}))

    with make_client(handler) as client:
        result = client.get_meta()

    assert result.entity == "parcels"
    assert result.total == 237


def test_every_request_has_a_timeout() -> None:
    handler, seen = sequence(page([1], 0, 1))

    with make_client(handler) as client:
        list(client.paginate("/v1/parcels", Parcel))

    assert seen[0].extensions["timeout"] == httpx.Timeout(5.0).as_dict()


def test_paginate_walks_every_page() -> None:
    with make_client(offset_server(total=7)) as client:
        records = list(client.paginate("/v1/parcels", Parcel, page_size=3))

    assert [record.id for record in records] == [1, 2, 3, 4, 5, 6, 7]


def test_paginate_skips_records_repeated_across_pages() -> None:
    with make_client(offset_server(total=7, quirk=True)) as client:
        records = list(client.paginate("/v1/parcels", Parcel, page_size=3))

    assert [record.id for record in records] == [1, 2, 3, 4, 5, 6, 7]


def test_paginate_stops_on_empty_page() -> None:
    handler, seen = sequence(page([1, 2], 0, 99), page([], 2, 99))

    with make_client(handler) as client:
        records = list(client.paginate("/v1/parcels", Parcel))

    assert len(records) == 2
    assert len(seen) == 2


def test_paginate_rejects_an_invalid_record() -> None:
    bad = {"items": [parcel(1), parcel(2, status="lost")], "offset": 0, "limit": 2, "total": 2}
    handler, _ = sequence(httpx.Response(200, json=bad))

    with make_client(handler) as client, pytest.raises(ApiResponseError, match="record 1"):
        list(client.paginate("/v1/parcels", Parcel))


def test_invalid_json_raises_response_error() -> None:
    handler, _ = sequence(httpx.Response(200, content=b"<html>oops</html>"))

    with make_client(handler) as client, pytest.raises(ApiResponseError, match="not JSON"):
        client.get_meta()


def test_retries_5xx_with_backoff_then_succeeds() -> None:
    sleeps: list[float] = []
    handler, seen = sequence(httpx.Response(503), httpx.Response(502), page([1], 0, 1))

    with make_client(handler, sleeps) as client:
        records = list(client.paginate("/v1/parcels", Parcel))

    assert len(records) == 1
    assert len(seen) == 3
    assert 0 <= sleeps[0] <= 1.0
    assert 0 <= sleeps[1] <= 2.0


def test_429_respects_retry_after_seconds() -> None:
    sleeps: list[float] = []
    handler, _ = sequence(httpx.Response(429, headers={"Retry-After": "7"}), page([1], 0, 1))

    with make_client(handler, sleeps) as client:
        list(client.paginate("/v1/parcels", Parcel))

    assert sleeps == [7.0]


def test_429_respects_retry_after_http_date() -> None:
    sleeps: list[float] = []
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=10), usegmt=True)
    handler, _ = sequence(httpx.Response(429, headers={"Retry-After": when}), page([1], 0, 1))

    with make_client(handler, sleeps) as client:
        list(client.paginate("/v1/parcels", Parcel))

    assert 8.0 <= sleeps[0] <= 10.0


def test_gives_up_when_retry_after_exceeds_max_delay() -> None:
    sleeps: list[float] = []
    handler, seen = sequence(httpx.Response(429, headers={"Retry-After": "3600"}))

    with make_client(handler, sleeps) as client, pytest.raises(ApiStatusError) as error:
        client.get_meta()

    assert error.value.status_code == 429
    assert sleeps == []
    assert len(seen) == 1


def test_gives_up_after_max_attempts() -> None:
    handler, seen = sequence(*(httpx.Response(500) for _ in range(3)))

    with make_client(handler) as client, pytest.raises(ApiStatusError) as error:
        client.get_meta()

    assert error.value.status_code == 500
    assert len(seen) == 3


def test_4xx_is_not_retried() -> None:
    handler, seen = sequence(httpx.Response(404, json={"detail": "unknown entity"}))

    with make_client(handler) as client, pytest.raises(ApiStatusError) as error:
        client.get_meta()

    assert error.value.status_code == 404
    assert len(seen) == 1


def test_timeouts_are_retried_then_reported() -> None:
    handler, seen = sequence(*(httpx.ReadTimeout("slow") for _ in range(3)))

    with make_client(handler) as client, pytest.raises(ApiConnectionError):
        client.get_meta()

    assert len(seen) == 3


def test_backoff_is_capped_and_jittered() -> None:
    policy = RetryPolicy(max_attempts=10, base_delay=1.0, max_delay=4.0)
    rng = random.Random(0)

    delays = [policy.backoff(attempt, rng) for attempt in range(8)]

    assert all(0 <= delay <= 4.0 for delay in delays)
    assert len(set(delays)) == len(delays)


def test_from_settings_uses_configured_base_url() -> None:
    settings = Settings(parcels_api_base_url=BASE_URL, parcels_api_timeout_seconds=2.5)

    with ApiClient.from_settings(settings) as client:
        assert client.base_url.host == "api.test"


def test_error_message_does_not_leak_response_body() -> None:
    body = json.dumps({"detail": "secret-internal-detail"})
    handler, _ = sequence(httpx.Response(400, content=body.encode()))

    with make_client(handler) as client, pytest.raises(ApiStatusError) as error:
        client.get_meta()

    assert "secret-internal-detail" not in str(error.value)
