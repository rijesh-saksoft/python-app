-- sql/schema.sql: the ONE definition of the database (Playbook DB-03).
-- To change the schema, edit this file in place. Do not create separate ALTER files.
-- Docker runs this file when the database is first created (see docker-compose.yml).
--
-- Parcel logistics: a parcel passes through hubs, and each stop at a hub records scan events.
--   parcels (main)  <-  hubs.parent_id  <-  scan_events.parent_id

CREATE TABLE IF NOT EXISTS parcels (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tracking_no     TEXT        NOT NULL UNIQUE,                -- natural key: what customers quote, and the upsert key
    recipient_name  TEXT        NOT NULL CHECK (recipient_name <> ''),
    status          TEXT        NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'delivered', 'returned', 'cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()          -- always timestamptz in UTC (DB-08)
);

-- One stop of one parcel at a hub.
CREATE TABLE IF NOT EXISTS hubs (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id   BIGINT        NOT NULL REFERENCES parcels (id) ON DELETE CASCADE,  -- stops mean nothing without their parcel
    name        TEXT          NOT NULL CHECK (name <> ''),                         -- the hub's name
    label       TEXT          NOT NULL CHECK (label <> ''),                        -- the hub's region
    amount      NUMERIC(12,2) NOT NULL CHECK (amount >= 0),                        -- handling cost; NUMERIC, never float, for money
    UNIQUE (parent_id, name)                                                       -- a parcel stops at a hub once; the upsert key
);

CREATE TABLE IF NOT EXISTS scan_events (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id   BIGINT      NOT NULL REFERENCES hubs (id) ON DELETE CASCADE,
    event       TEXT        NOT NULL CHECK (event IN ('arrived', 'sorted', 'departed', 'exception')),
    occurred_at TIMESTAMPTZ NOT NULL,
    UNIQUE (parent_id, occurred_at, event)                                         -- the same scan is never stored twice
);

-- One reason per index (DB-04). The UNIQUE constraints above already create these indexes:
--   parcels (tracking_no):                     look up a parcel by its tracking number.
--   hubs (parent_id, name):                    find a parcel's stops; also serves the foreign key,
--                                              which PostgreSQL does not index on its own.
--   scan_events (parent_id, occurred_at, ...): a stop's scans in time order, newest first when
--                                              read backwards; also serves the foreign key.

-- "Active parcels, newest first": filter on status and read already sorted by created_at.
CREATE INDEX IF NOT EXISTS idx_parcels_status_created_at ON parcels (status, created_at DESC);
