#!/usr/bin/env bash
# The whole online migration under live load: pgbench (8 clients, 400 tx/s, 4:1 insert:lookup)
# runs throughout; per-second min/max latency is logged and split by phase.
#   ./migrate.sh            CHECK constraint validated first (the article's path)
#   ./migrate.sh nocheck    skip the CHECK: ATTACH must scan the table under lock
set -euo pipefail
cd "$(dirname "$0")"
C=pg18-partition; MODE="${1:-check}"; OUT="run-$MODE"
mkdir -p "$OUT"; rm -f "$OUT"/*
for f in insert.sql lookup.sql prepare.sql parent.sql swap.sql; do docker cp "$f" $C:/$f; done
q() { docker exec $C psql -U postgres -X -v ON_ERROR_STOP=1 "$@"; }
q -qc "DROP DATABASE IF EXISTS run" -c "CREATE DATABASE run TEMPLATE seed"
q -d run -qc "VACUUM ANALYZE parcel_scan" -c "SELECT count(*) FROM parcel_scan" >/dev/null   # warm
docker exec $C bash -c "rm -f /tmp/pgb*; cd /tmp && pgbench -U postgres -n -c 8 -j 4 -R 400 -T 75 \
  -f /insert.sql@4 -f /lookup.sql@1 -l --log-prefix=pgb --aggregate-interval=1 run > /tmp/pgbench.out 2>&1" &
mark() { echo "$1 $(date +%s.%N)" >> "$OUT/phases.txt"; }
sleep 10; mark baseline_end
if [[ $MODE == check ]]; then
  mark validate; q -d run -f /prepare.sql | tee "$OUT/prepare.txt"; mark prepare_end
else
  mark index; q -d run -c "\timing on" -c "CREATE UNIQUE INDEX CONCURRENTLY parcel_scan_id_time_key ON parcel_scan (scan_id, scanned_at)" | tee "$OUT/prepare.txt"; mark prepare_end
fi
sleep 5
q -d run -qf /parent.sql
mark swap; q -d run -f /swap.sql | tee "$OUT/swap.txt"; mark swap_end
wait
docker exec $C bash -c 'cat /tmp/pgb.*' > "$OUT/latency.log"
docker exec $C cat /tmp/pgbench.out > "$OUT/pgbench.txt"
q -d run -c "SELECT tableoid::regclass, count(*) FROM parcel_scan WHERE scanned_at > now() - interval '2 minutes' GROUP BY 1" | tee "$OUT/where_rows_went.txt"
python3 phases.py "$OUT" | tee "$OUT/phases-report.txt"
