-- Three copies of the same webhook delivery log; only the primary key differs.
CREATE EXTENSION IF NOT EXISTS pgstattuple;

DROP TABLE IF EXISTS delivery_serial, delivery_v4, delivery_v7;

CREATE TABLE delivery_serial (
    delivery_id   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    endpoint_id   integer     NOT NULL,
    status_code   smallint    NOT NULL,
    payload_bytes integer     NOT NULL,
    attempted_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_v4 (
    delivery_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id   integer     NOT NULL,
    status_code   smallint    NOT NULL,
    payload_bytes integer     NOT NULL,
    attempted_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_v7 (LIKE delivery_v4 INCLUDING ALL);
ALTER TABLE delivery_v7 ALTER COLUMN delivery_id SET DEFAULT uuidv7();
