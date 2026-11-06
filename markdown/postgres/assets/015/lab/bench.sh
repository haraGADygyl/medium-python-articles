#!/usr/bin/env bash
# Plan and latency of revenue.sql under three statistics states.
# pgbench: 20 transactions, one client, parallel query off (PGOPTIONS).
set -euo pipefail
C=pg18-extstats
docker cp "$(dirname "$0")/revenue.sql" $C:/revenue.sql
psql_() { docker exec -e PGOPTIONS='-c max_parallel_workers_per_gather=0' $C psql -U postgres -X "$@"; }
state() {
  echo "=== $1"
  psql_ -c "EXPLAIN (ANALYZE, BUFFERS, SUMMARY OFF, TIMING OFF) $(cat "$(dirname "$0")/revenue.sql")" | grep -E 'Join|Loop|Materialize|Hash|rows=' | sed 's/  (cost=[^)]*)//'
  docker exec -e PGOPTIONS='-c max_parallel_workers_per_gather=0' $C pgbench -U postgres -n -f /revenue.sql -t 20 postgres 2>/dev/null | grep -E 'latency average'
}
psql_ -qc "DROP STATISTICS IF EXISTS charge_session_place, charge_session_vehicle" -c "ANALYZE charge_session"
state "no extended statistics"
psql_ -qc "CREATE STATISTICS charge_session_place (dependencies) ON city, state FROM charge_session" \
      -c "CREATE STATISTICS charge_session_vehicle (dependencies) ON vehicle_make, vehicle_model, connector FROM charge_session" \
      -c "ANALYZE charge_session"
state "dependencies"
psql_ -qc "ALTER STATISTICS charge_session_place RENAME TO x1" -c "DROP STATISTICS x1, charge_session_vehicle" \
      -c "CREATE STATISTICS charge_session_place (ndistinct, dependencies, mcv) ON city, state FROM charge_session" \
      -c "CREATE STATISTICS charge_session_vehicle (ndistinct, dependencies, mcv) ON vehicle_make, vehicle_model, connector FROM charge_session" \
      -c "ANALYZE charge_session"
state "ndistinct + dependencies + mcv"
