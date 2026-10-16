\set id random(1, 300000)
UPDATE accounts SET last_seen = now() WHERE user_id = :id;
