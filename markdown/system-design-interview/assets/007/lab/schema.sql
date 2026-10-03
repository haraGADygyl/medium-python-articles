DROP TABLE IF EXISTS entry, account, checkpoint;
CREATE TABLE account (
    id      bigint PRIMARY KEY,
    kind    text   NOT NULL,           -- wallet, merchant, platform
    balance bigint NOT NULL            -- cents
);
CREATE TABLE entry (
    id         bigserial PRIMARY KEY,
    account_id bigint NOT NULL,
    amount     bigint NOT NULL,        -- signed cents
    xid        xid8   NOT NULL DEFAULT pg_current_xact_id(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX entry_account_xid ON entry (account_id, xid) INCLUDE (amount);
CREATE INDEX entry_account_id  ON entry (account_id, id)  INCLUDE (amount);

INSERT INTO account VALUES (0, 'platform', 0);
INSERT INTO account SELECT g, 'wallet', 1000000 FROM generate_series(1, 1000000) g;
INSERT INTO account SELECT g, 'merchant', 0 FROM generate_series(1000001, 1010000) g;
VACUUM ANALYZE account;
