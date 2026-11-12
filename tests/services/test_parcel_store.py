"""Parcel queries against a real PostgreSQL: the lab container, never a shared database.

Run with:  POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5434 uv run pytest --lab-db-env=~/pg-lab.env
Keep the "=": with a space, pytest takes the file path for a test folder before it knows the
option. Without --lab-db-env, or when the database cannot be reached, these tests are skipped.
Every test runs in a transaction that is rolled back, so the lab data never changes.
"""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.config import Settings
from app.services.database import connect
from app.services.parcel_store import find_parcels_by_recipient, upsert_parcel

ATTACK_ALL_ROWS = "' OR '1'='1"
ATTACK_UNION = "' UNION SELECT current_user, version(), 'leaked' --"
ATTACK_DELETE = "x'; DELETE FROM parcels WHERE tracking_no LIKE 'TEST-%'; --"


def find_parcels_unsafe(conn: psycopg.Connection, recipient: str) -> list[tuple[str, str, str]]:
    """DELIBERATELY VULNERABLE, for the demonstration only: the input is pasted into the SQL."""
    query = (
        "SELECT tracking_no, recipient_name, status FROM parcels "  # noqa: S608 - the flaw under test
        f"WHERE recipient_name = '{recipient}' LIMIT 50"
    )
    with conn.cursor() as cur:
        # psycopg's typing rightly rejects SQL that is not a literal; this demo needs it.
        cur.execute(query)  # type: ignore[arg-type]
        return cur.fetchall() if cur.description else []


@pytest.fixture
def conn(request: pytest.FixtureRequest) -> Iterator[psycopg.Connection]:
    env_file = request.config.getoption("--lab-db-env")
    if env_file is None:
        pytest.skip("database tests need --lab-db-env")
    settings = Settings(_env_file=Path(env_file).expanduser())  # type: ignore[call-arg]
    try:
        connection = connect(settings)
    except psycopg.OperationalError as exc:
        pytest.skip(f"lab database not reachable: {exc}")
    with connection, connection.transaction(force_rollback=True):
        upsert_parcel(connection, "TEST-0001", "Test Person (invented)", "active")
        upsert_parcel(connection, "TEST-0002", "Other Person (invented)", "delivered")
        yield connection


def count_test_parcels(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM parcels WHERE tracking_no LIKE 'TEST-%'")
        row = cur.fetchone()
    assert row is not None
    return row[0]


def test_unsafe_query_returns_every_row_for_an_always_true_input(conn: psycopg.Connection) -> None:
    rows = find_parcels_unsafe(conn, ATTACK_ALL_ROWS)

    assert len(rows) > 1
    assert any(name != ATTACK_ALL_ROWS for _, name, _ in rows)


def test_unsafe_query_leaks_data_from_outside_the_table(conn: psycopg.Connection) -> None:
    rows = find_parcels_unsafe(conn, ATTACK_UNION)

    assert any(status == "leaked" and "PostgreSQL" in name for _, name, status in rows)


def test_unsafe_query_runs_a_second_statement(conn: psycopg.Connection) -> None:
    find_parcels_unsafe(conn, ATTACK_DELETE)

    assert count_test_parcels(conn) == 0


@pytest.mark.parametrize("attack", [ATTACK_ALL_ROWS, ATTACK_UNION, ATTACK_DELETE])
def test_parameterised_query_treats_every_attack_as_a_plain_name(
    conn: psycopg.Connection, attack: str
) -> None:
    assert find_parcels_by_recipient(conn, attack) == []
    assert count_test_parcels(conn) == 2


def test_parameterised_query_finds_a_real_name(conn: psycopg.Connection) -> None:
    rows = find_parcels_by_recipient(conn, "Test Person (invented)")

    assert [(row.tracking_no, row.status) for row in rows] == [("TEST-0001", "active")]


def test_upsert_twice_keeps_one_row_with_the_latest_values(conn: psycopg.Connection) -> None:
    first = upsert_parcel(conn, "TEST-0003", "New Person (invented)", "active")
    second = upsert_parcel(conn, "TEST-0003", "New Person (invented)", "delivered")

    assert first.inserted
    assert not second.inserted
    assert first.id == second.id
    assert [row.status for row in find_parcels_by_recipient(conn, "New Person (invented)")] == [
        "delivered"
    ]


def test_search_limit_is_capped(conn: psycopg.Connection) -> None:
    with pytest.raises(ValueError, match="limit"):
        find_parcels_by_recipient(conn, "anyone", limit=10_000)
