SELECT count(*) FROM accounts WHERE last_seen > now() - interval '60 seconds';
