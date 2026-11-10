-- sql/lab/exercises.sql: the 8 day-7 query exercises, variant 3 (parcel logistics).
-- Run against the lab database after schema.sql and lab/seed.sql:
--   docker exec -i pg-lab psql -U parcels -d parcels < sql/lab/exercises.sql
-- Every list query names its columns and has a LIMIT (DB rules).

\echo '1. The first 10 active parcels, newest first'
-- Served by idx_parcels_status_created_at: Postgres reads the 10 rows already in order and stops.
SELECT id, tracking_no, recipient_name, created_at
FROM parcels
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 10;

\echo '2. Parcels per status'
SELECT status, count(*) AS parcels
FROM parcels
GROUP BY status
ORDER BY parcels DESC
LIMIT 10;

\echo '3. Each hub stop with the name of its parcel'
SELECT h.id, h.name AS hub, h.label, h.amount, p.tracking_no, p.recipient_name
FROM hubs AS h
JOIN parcels AS p ON p.id = h.parent_id
ORDER BY h.id
LIMIT 20;

\echo '4. Parcels with more than 2 hub stops'
SELECT p.id, p.tracking_no, count(*) AS stops
FROM parcels AS p
JOIN hubs AS h ON h.parent_id = p.id
GROUP BY p.id, p.tracking_no
HAVING count(*) > 2
ORDER BY stops DESC, p.id
LIMIT 20;

\echo '5. Parcels with no hub stop'
-- LEFT JOIN keeps every parcel; where no stop matched, the hub columns are NULL.
SELECT p.id, p.tracking_no, p.recipient_name, p.status
FROM parcels AS p
LEFT JOIN hubs AS h ON h.parent_id = p.id
WHERE h.id IS NULL
ORDER BY p.id
LIMIT 20;

\echo '6. Handling cost per region, only regions above 1000'
-- HAVING filters groups after they are totalled; WHERE could only filter single rows.
SELECT label, sum(amount) AS total_amount
FROM hubs
GROUP BY label
HAVING sum(amount) > 1000
ORDER BY total_amount DESC
LIMIT 20;

\echo '7. Each parcel''s stops ranked by handling cost'
-- RANK gives equal amounts the same rank and then skips; ROW_NUMBER would break ties
-- arbitrarily, DENSE_RANK would not skip.
SELECT p.tracking_no, h.name AS hub, h.amount,
       RANK() OVER (PARTITION BY h.parent_id ORDER BY h.amount DESC) AS amount_rank
FROM hubs AS h
JOIN parcels AS p ON p.id = h.parent_id
ORDER BY p.tracking_no, amount_rank
LIMIT 20;

\echo '8. The latest scan for every hub stop'
-- The CTE numbers each stop's scans newest first; the outer query keeps number 1. LEFT JOIN
-- keeps a stop that has no scan yet. id breaks a tie between scans at the same moment.
WITH latest AS (
    SELECT parent_id, event, occurred_at,
           ROW_NUMBER() OVER (PARTITION BY parent_id ORDER BY occurred_at DESC, id DESC) AS position
    FROM scan_events
)
SELECT h.id, h.name AS hub, l.event, l.occurred_at
FROM hubs AS h
LEFT JOIN latest AS l ON l.parent_id = h.id AND l.position = 1
ORDER BY h.id
LIMIT 20;

-- EXPLAIN before and after the index on hubs (parent_id).
-- The index comes from UNIQUE (parent_id, name) in schema.sql. "Before" drops it inside a
-- transaction and rolls back: PostgreSQL DDL is transactional, so nothing is changed.
--
-- Measured on the seed data (20,000 parcels, 58,020 stops):
--   Exercises 3 and 4 as written read every row, so the plan is the same with or without the
--   index: a sequential scan and hash join is the cheapest way to read everything.
--   One parcel's stops: with the index 6 pages and ~0.1 ms (Index Scan); without it
--   495 pages and ~3.5 ms (Seq Scan on hubs). An index pays off when a query is selective.

\echo 'EXPLAIN with the index'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, BUFFERS)
SELECT p.id, p.tracking_no, count(*) AS stops
FROM parcels AS p JOIN hubs AS h ON h.parent_id = p.id
GROUP BY p.id, p.tracking_no HAVING count(*) > 2
ORDER BY stops DESC, p.id LIMIT 20;

EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, BUFFERS)
SELECT h.id, h.name AS hub, p.tracking_no, p.recipient_name
FROM hubs AS h JOIN parcels AS p ON p.id = h.parent_id
WHERE p.tracking_no = 'PX00012345'
LIMIT 20;

BEGIN;
ALTER TABLE hubs DROP CONSTRAINT hubs_parent_id_name_key;

\echo 'EXPLAIN without the index'
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, BUFFERS)
SELECT p.id, p.tracking_no, count(*) AS stops
FROM parcels AS p JOIN hubs AS h ON h.parent_id = p.id
GROUP BY p.id, p.tracking_no HAVING count(*) > 2
ORDER BY stops DESC, p.id LIMIT 20;

EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, BUFFERS)
SELECT h.id, h.name AS hub, p.tracking_no, p.recipient_name
FROM hubs AS h JOIN parcels AS p ON p.id = h.parent_id
WHERE p.tracking_no = 'PX00012345'
LIMIT 20;

ROLLBACK;
