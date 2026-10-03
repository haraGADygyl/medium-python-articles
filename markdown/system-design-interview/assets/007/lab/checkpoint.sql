CREATE TABLE IF NOT EXISTS checkpoint (
    account_id bigint      NOT NULL,
    seq        bigint      NOT NULL,
    balance    bigint      NOT NULL,
    upto_id    bigint,               -- naive boundary: entries with id <= upto_id
    below_xid  xid8,                 -- watermark boundary: entries with xid < below_xid
    included   bigint      NOT NULL, -- entries counted so far, for the audit
    PRIMARY KEY (account_id, seq)
);
INSERT INTO account VALUES (7, 'platform', 0) ON CONFLICT DO NOTHING;
