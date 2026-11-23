-- A table with GENERATED ALWAYS AS IDENTITY cannot be attached as a partition
-- ("The new partition may not contain an identity column"). The fix: move the identity to the parent inside the swap.
DROP DATABASE IF EXISTS idt;
CREATE DATABASE idt;
\c idt
CREATE TABLE ev (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, at timestamptz NOT NULL);
INSERT INTO ev (at) SELECT now() - g * interval '1 hour' FROM generate_series(1,100) g;
ALTER TABLE ev ADD CONSTRAINT ev_bound CHECK (at < '2026-12-01');
CREATE UNIQUE INDEX ev_id_at ON ev (id, at);
CREATE TABLE ev_new (LIKE ev INCLUDING IDENTITY) PARTITION BY RANGE (at);
ALTER TABLE ev_new ADD PRIMARY KEY (id, at);
BEGIN;
ALTER TABLE ev RENAME TO ev_legacy;
ALTER TABLE ev_legacy DROP CONSTRAINT ev_pkey, ADD CONSTRAINT ev_legacy_pkey PRIMARY KEY USING INDEX ev_id_at;
ALTER TABLE ev_legacy ALTER COLUMN id DROP IDENTITY;
DO $$ BEGIN
  EXECUTE format('ALTER TABLE ev_new ALTER COLUMN id RESTART WITH %s',
                 (SELECT max(id) + 1 FROM ev_legacy));
END $$;
ALTER TABLE ev_new RENAME TO ev;
ALTER TABLE ev ATTACH PARTITION ev_legacy FOR VALUES FROM (MINVALUE) TO ('2026-12-01');
COMMIT;
INSERT INTO ev (at) VALUES (now()) RETURNING id, tableoid::regclass;
\d ev
\c postgres
DROP DATABASE idt;
