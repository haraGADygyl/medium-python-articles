#!/usr/bin/env bash
# The lock queue: a 20 s report holds ACCESS SHARE; the swap's ACCESS EXCLUSIVE request queues
# behind it and every later insert queues behind the swap.
#   t=8 s  swap with lock_timeout = 2s   (gives up, rolls back)
#   t=14 s swap with no lock_timeout     (waits for the report, then commits)
set -euo pipefail
cd "$(dirname "$0")"
C=pg18-partition; OUT=run-lockqueue
mkdir -p "$OUT"; rm -f "$OUT"/*
sed '/lock_timeout/d' swap.sql > /tmp/swap-notimeout.sql
docker cp /tmp/swap-notimeout.sql $C:/swap-notimeout.sql
for f in insert.sql lookup.sql prepare.sql parent.sql swap.sql report.sql; do docker cp "$f" $C:/$f; done
q() { docker exec $C psql -U postgres -X "$@"; }
q -qc "DROP DATABASE IF EXISTS run" -c "CREATE DATABASE run TEMPLATE seed"
q -d run -q -f /prepare.sql >/dev/null; q -d run -qf /parent.sql
docker exec $C bash -c "rm -f /tmp/pgb*; cd /tmp && pgbench -U postgres -n -c 8 -j 4 -R 400 -T 40 \
  -f /insert.sql@4 -f /lookup.sql@1 -l --log-prefix=pgb --aggregate-interval=1 run > /tmp/pgbench.out 2>&1" &
mark() { echo "$1 $(date +%s.%N)" >> "$OUT/phases.txt"; }
sleep 3; mark report_starts
q -d run -qf /report.sql > /dev/null &
sleep 5; mark swap_2s_timeout
q -d run -f /swap.sql > "$OUT/swap-timeout.txt" 2>&1 || true; mark retry_gap
sleep 4; mark swap_no_timeout
q -d run -f /swap-notimeout.sql > "$OUT/swap-notimeout.txt" 2>&1; mark after
sleep 8; mark end
wait
docker exec $C bash -c 'cat /tmp/pgb.*' > "$OUT/latency.log"
docker exec $C cat /tmp/pgbench.out > "$OUT/pgbench.txt"
python3 phases.py "$OUT" | tee "$OUT/phases-report.txt"
