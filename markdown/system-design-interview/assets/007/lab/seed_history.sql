-- Four platform-style accounts with 10^4 .. 10^7 entries of history each.
INSERT INTO account VALUES (-1, 'platform', 0), (-2, 'platform', 0),
                           (-3, 'platform', 0), (-4, 'platform', 0)
ON CONFLICT DO NOTHING;
INSERT INTO entry (account_id, amount)
SELECT -1, 1 + g % 97 FROM generate_series(1, 10000) g;
INSERT INTO entry (account_id, amount)
SELECT -2, 1 + g % 97 FROM generate_series(1, 100000) g;
INSERT INTO entry (account_id, amount)
SELECT -3, 1 + g % 97 FROM generate_series(1, 1000000) g;
INSERT INTO entry (account_id, amount)
SELECT -4, 1 + g % 97 FROM generate_series(1, 10000000) g;
VACUUM ANALYZE entry;
