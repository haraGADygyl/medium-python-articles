-- What uuidv7() gives you beyond insert locality, and what it gives away.
\pset footer off

-- Version and embedded timestamp
SELECT uuidv7() AS v7, uuid_extract_version(uuidv7()) AS ver,
       uuid_extract_timestamp(uuidv7()) AS created;
SELECT uuidv4() AS v4, uuid_extract_version(uuidv4()) AS ver,
       uuid_extract_timestamp(uuidv4()) AS created;

-- Monotonic within one backend, even inside the same millisecond
WITH ids AS (
    SELECT n, uuidv7() AS id FROM generate_series(1, 1000000) AS n
)
SELECT count(*) AS ids,
       count(DISTINCT uuid_extract_timestamp(id)) AS distinct_ms,
       bool_and(id > prev) AS strictly_increasing
FROM (SELECT id, lag(id) OVER (ORDER BY n) AS prev FROM ids) AS t
WHERE prev IS NOT NULL;

-- The shift argument back-dates the timestamp (the rest stays random)
SELECT uuid_extract_timestamp(uuidv7(interval '-30 days')) AS back_dated;

-- Anyone holding an id can read when the row was created
SELECT delivery_id, uuid_extract_timestamp(delivery_id) AS leaked_created_at
FROM delivery_v7 ORDER BY delivery_id DESC LIMIT 1;

-- "Latest 50 deliveries": no attempted_at index on either table
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT delivery_id, endpoint_id, status_code
FROM delivery_v4 ORDER BY attempted_at DESC LIMIT 50;

EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT delivery_id, endpoint_id, status_code
FROM delivery_v7 ORDER BY delivery_id DESC LIMIT 50;
