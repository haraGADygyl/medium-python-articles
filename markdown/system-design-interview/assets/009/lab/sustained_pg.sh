#!/usr/bin/env bash
# 10,000 heartbeats/s for 180 s, progress every 15 s, 2 interleaved rounds.
set -euo pipefail
PSQL="docker exec -i presence-pg psql -U postgres -qAt"
for round in 1 2; do
  for config in no_index index; do
    $PSQL < schema.sql 2>/dev/null
    [[ $config == index ]] && $PSQL -c "CREATE INDEX accounts_last_seen ON accounts (last_seen)"
    $PSQL -c "SELECT pg_stat_reset(); CHECKPOINT" >/dev/null
    before=$($PSQL -c "SELECT pg_current_wal_lsn()")
    echo "== round $round $config"
    docker exec presence-pg pgbench -U postgres -n -c 16 -j 4 -T 180 -R 10000 -P 15 \
      -f /tmp/heartbeat.sql postgres 2>&1 | grep -E "^progress|^tps|lag:|latency average"
    after=$($PSQL -c "SELECT pg_current_wal_lsn()")
    $PSQL -c "SELECT 'updates ' || n_tup_upd || '  hot% ' || round(100.0 * n_tup_hot_upd / greatest(n_tup_upd,1), 1) ||
              '  wal bytes/update ' || round(pg_wal_lsn_diff('$after','$before') / greatest(n_tup_upd,1)) ||
              '  wal MB ' || round(pg_wal_lsn_diff('$after','$before') / 1048576.0) ||
              '  heap MB ' || round(pg_relation_size('accounts')/1048576.0) ||
              '  indexes MB ' || round(pg_indexes_size('accounts')/1048576.0) ||
              '  autovacuums ' || autovacuum_count
              FROM pg_stat_user_tables WHERE relname = 'accounts'"
  done
done
