#!/usr/bin/env bash
# Rebuild the lab from nothing and run every experiment in order.
set -euo pipefail
cd "$(dirname "$0")"
docker rm -f bal-pg >/dev/null 2>&1 || true
docker run -d --name bal-pg -e POSTGRES_PASSWORD=demo -p 5471:5432 --shm-size=1g \
  postgres:17 -c shared_buffers=1GB -c max_connections=200 \
  -c max_wal_size=16GB -c checkpoint_timeout=30min >/dev/null
until docker exec bal-pg pg_isready -U postgres -q; do sleep 1; done; sleep 2
docker exec -i bal-pg psql -U postgres -q -v ON_ERROR_STOP=1 < schema.sql 2>/dev/null
docker exec -i bal-pg psql -U postgres -q -v ON_ERROR_STOP=1 < checkpoint.sql
docker cp bench bal-pg:/bench >/dev/null
./bench/run.sh | tee output-pgbench.txt
docker exec -i bal-pg psql -U postgres -q -v ON_ERROR_STOP=1 < seed_history.sql
python3 sum_latency.py | tee output-sum-latency.txt
DURATION=30 python3 race.py naive | tee output-race-naive.txt
DURATION=30 python3 race.py watermark | tee output-race-watermark.txt
python3 stall.py | tee output-stall.txt
for _ in 1 2 3; do python3 overdraft.py; done | tee output-overdraft.txt
