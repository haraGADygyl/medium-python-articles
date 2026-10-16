#!/usr/bin/env bash
# Unthrottled heartbeat ceiling, 16 clients, 30 s, 3 interleaved rounds,
# plus wait events sampled every 100 ms during each run.
set -euo pipefail
PSQL="docker exec -i presence-pg psql -U postgres -qAt"
for round in 1 2 3; do
  for config in no_index index; do
    $PSQL < schema.sql 2>/dev/null
    [[ $config == index ]] && $PSQL -c "CREATE INDEX accounts_last_seen ON accounts (last_seen)"
    $PSQL -c "CHECKPOINT"
    $PSQL -c "CREATE TABLE IF NOT EXISTS waits (config text, ev text)" 2>/dev/null
    docker exec presence-pg pgbench -U postgres -n -c 16 -j 4 -T 30 -f /tmp/heartbeat.sql postgres > /tmp/pgb_$$.txt 2>&1 &
    pid=$!
    sleep 5
    for i in $(seq 1 200); do
      $PSQL -c "SELECT coalesce(wait_event_type || ':' || wait_event, 'CPU') FROM pg_stat_activity
                WHERE query LIKE 'UPDATE accounts%' AND state = 'active'" >> waits_$config.txt
      sleep 0.1
    done
    wait $pid
    tps=$(grep -oP '^tps = \K[0-9.]+' /tmp/pgb_$$.txt)
    lat=$(grep -oP 'latency average = \K[0-9.]+' /tmp/pgb_$$.txt)
    printf "round %d  %-8s  %8.0f updates/s  %6s ms avg\n" $round $config $tps $lat
  done
done
for config in no_index index; do
  echo "-- wait events, $config (samples of active heartbeat backends)"
  sort waits_$config.txt | uniq -c | sort -rn | head -5
done
rm -f waits_*.txt
