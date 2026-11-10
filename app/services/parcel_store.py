"""Parcel queries. Values always travel as parameters (%s), never inside the SQL text, so
input such as "' OR '1'='1" is compared as a plain name and cannot change the query (DB rules).
"""

from dataclasses import dataclass
from typing import Literal

import psycopg
from psycopg.rows import class_row

ParcelStatus = Literal["active", "delivered", "returned", "cancelled"]
MAX_LIMIT = 200


@dataclass(frozen=True, slots=True)
class ParcelRow:
    tracking_no: str
    recipient_name: str
    status: str


@dataclass(frozen=True, slots=True)
class UpsertResult:
    id: int
    inserted: bool


def find_parcels_by_recipient(
    conn: psycopg.Connection, recipient: str, limit: int = 50
) -> list[ParcelRow]:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    with conn.cursor(row_factory=class_row(ParcelRow)) as cur:
        cur.execute(
            "SELECT tracking_no, recipient_name, status FROM parcels "
            "WHERE recipient_name = %s ORDER BY tracking_no LIMIT %s",
            (recipient, limit),
        )
        return cur.fetchall()


def upsert_parcel(
    conn: psycopg.Connection, tracking_no: str, recipient_name: str, status: ParcelStatus
) -> UpsertResult:
    """Insert the parcel, or update it if the tracking number exists, so a re-run is safe."""
    with conn.cursor(row_factory=class_row(UpsertResult)) as cur:
        cur.execute(
            "INSERT INTO parcels (tracking_no, recipient_name, status) VALUES (%s, %s, %s) "
            "ON CONFLICT (tracking_no) DO UPDATE "
            "SET recipient_name = EXCLUDED.recipient_name, status = EXCLUDED.status "
            # xmax is 0 only on a newly inserted row: how PostgreSQL tells insert from update.
            "RETURNING id, (xmax = 0) AS inserted",
            (tracking_no, recipient_name, status),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("upsert returned no row")
    return row
