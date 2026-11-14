-- Run on the primary; the replica gets it through streaming replication.
DROP TABLE IF EXISTS orders, carts, import_rows, heartbeat;

CREATE TABLE orders (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id int         NOT NULL,
    status      text        NOT NULL DEFAULT 'placed',
    total_cents int         NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO orders (customer_id, total_cents, created_at)
SELECT (random() * 199999)::int + 1,
       (random() * 40000)::int + 500,
       now() - random() * interval '365 days'
FROM generate_series(1, 1000000);

CREATE INDEX orders_customer_idx ON orders (customer_id, created_at);

-- Shopping carts; a cleanup job deletes the abandoned ones.
CREATE TABLE carts (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id int         NOT NULL,
    items       jsonb       NOT NULL,
    updated_at  timestamptz NOT NULL
);

-- Bulk-import target for the "busy primary" load.
CREATE TABLE import_rows (
    id      bigint,
    sku     text,
    payload text
);

ALTER TABLE carts SET (autovacuum_enabled = off);
ALTER TABLE import_rows SET (autovacuum_enabled = off);
VACUUM ANALYZE orders;

-- One row the lab updates every 100 ms on the primary to measure replica lag.
CREATE TABLE IF NOT EXISTS heartbeat (id int PRIMARY KEY, ts timestamptz NOT NULL);
INSERT INTO heartbeat VALUES (1, clock_timestamp())
ON CONFLICT (id) DO NOTHING;
