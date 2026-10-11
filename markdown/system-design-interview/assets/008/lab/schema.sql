-- Two databases in one container, and no code path that touches both in one
-- transaction: `shop` is ours, `provider` belongs to the payment provider.
DROP DATABASE IF EXISTS shop;
DROP DATABASE IF EXISTS provider;
CREATE DATABASE shop;
CREATE DATABASE provider;

\c provider
CREATE TABLE charge (
    id          bigserial PRIMARY KEY,
    key         text NOT NULL UNIQUE,      -- the idempotency key
    amount      int  NOT NULL,
    status      text NOT NULL,             -- succeeded | declined
    inbound_ms  int  NOT NULL,             -- time in flight before it arrived
    created_at  timestamptz NOT NULL DEFAULT clock_timestamp()
);

\c shop
CREATE TABLE stock (
    sku  text PRIMARY KEY,
    qty  int NOT NULL CHECK (qty >= 0)
);
INSERT INTO stock
SELECT 'SKU-' || g, 1000000 FROM generate_series(1, 500) g;
INSERT INTO stock VALUES ('HOT-1', 1000000);

-- the saga's state, one row per checkout
CREATE TABLE checkout (
    key         text PRIMARY KEY,
    sku         text NOT NULL,
    amount      int  NOT NULL,
    card        text NOT NULL,
    state       text NOT NULL,             -- pending | completed | failed
    charge_id   bigint,
    resolved_by text,                      -- worker | sweeper
    created_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
    resolved_at timestamptz
);
CREATE INDEX checkout_pending ON checkout (created_at) WHERE state = 'pending';

CREATE TABLE orders (
    id            bigserial PRIMARY KEY,
    checkout_key  text NOT NULL UNIQUE,
    sku           text NOT NULL,
    amount        int  NOT NULL,
    charge_id     bigint
);
