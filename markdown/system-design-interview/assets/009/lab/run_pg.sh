#!/usr/bin/env bash
# Heartbeats as UPDATE ... SET last_seen = now(), 300k connected users every 30 s
# = 10,000 updates/s. Two configurations: no index on last_seen, and an index.
set -euo pipefail
PSQL="docker exec -i presence-pg psql -U postgres -qAt"
docker cp heartbeat.sql presence-pg:/tmp/heartbeat.sql >/dev/null
docker cp online.sql presence-pg:/tmp/online.sql >/dev/null
for config in no_index index; do
  $PSQL < schema.sql
  [[ $config == index ]] && $PSQL -c "CREATE INDEX accounts_last_seen ON accounts (last_seen)"
  $PSQL -c "SELECT pg_stat_reset(); CHECKPOINT"
  before=$($PSQL -c "SELECT pg_current_wal_lsn()")
  sizes0=$($PSQL -c "SELECT pg_relation_size('accounts'), pg_indexes_size('accounts')")
  echo "== $config: rate 10000/s, 16 clients, 60 s"
  docker exec presence-pg pgbench -U postgres -n -c 16 -j 4 -T 60 -R 10000 \
    -f /tmp/heartbeat.sql postgres 2>&1 | grep -E "tps|latency|lag|late|processed"
  after=$($PSQL -c "SELECT pg_current_wal_lsn()")
  $PSQL -c "SELECT 'updates ' || n_tup_upd || '  hot ' || n_tup_hot_upd ||
            '  hot% ' || round(100.0 * n_tup_hot_upd / greatest(n_tup_upd,1), 1) ||
            '  wal bytes/update ' || round(pg_wal_lsn_diff('$after','$before') / greatest(n_tup_upd,1))
            FROM pg_stat_user_tables WHERE relname = 'accounts'"
  $PSQL -c "SELECT 'heap MB ' || round($(echo $sizes0 | cut -d'|' -f1)/1048576.0) || ' -> ' || round(pg_relation_size('accounts')/1048576.0) ||
            '  indexes MB ' || round($(echo $sizes0 | cut -d'|' -f2)/1048576.0) || ' -> ' || round(pg_indexes_size('accounts')/1048576.0)"
  echo "-- online count, 20 runs while 10000/s heartbeats continue"
  docker exec presence-pg pgbench -U postgres -n -c 16 -j 4 -T 25 -R 10000 -f /tmp/heartbeat.sql postgres >/dev/null 2>&1 &
  sleep 3
  docker exec presence-pg pgbench -U postgres -n -c 1 -t 20 -f /tmp/online.sql -r postgres 2>&1 | grep -E "latency average"
  $PSQL -c "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) SELECT count(*) FROM accounts WHERE last_seen > now() - interval '60 seconds'" | grep -E "Scan|Heap Fetches|Execution|Buffers" | head -6
  wait
  echo "-- unthrottled ceiling, 16 clients, 30 s"
  docker exec presence-pg pgbench -U postgres -n -c 16 -j 4 -T 30 -f /tmp/heartbeat.sql postgres 2>&1 | grep -E "^tps|latency average"
done
