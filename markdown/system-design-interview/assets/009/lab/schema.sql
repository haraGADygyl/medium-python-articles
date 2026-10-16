-- 1M accounts on a tutoring marketplace; ids 1..300000 are connected right now
DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (
    user_id      bigint PRIMARY KEY,
    display_name text NOT NULL,
    role         text NOT NULL,
    timezone     text NOT NULL,
    last_seen    timestamptz NOT NULL
);
INSERT INTO accounts
SELECT g, 'user_' || g, CASE WHEN g % 10 = 0 THEN 'tutor' ELSE 'student' END,
       'Europe/Sofia',
       CASE WHEN g <= 300000 THEN now() ELSE now() - interval '3 days' END
FROM generate_series(1, 1000000) AS g;
VACUUM ANALYZE accounts;
