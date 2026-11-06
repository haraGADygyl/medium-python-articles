#!/usr/bin/env bash
# Full EXPLAIN ANALYZE of revenue.sql before and after extended statistics -> plans.txt
set -euo pipefail
C=pg18-extstats
cd "$(dirname "$0")"
psql_() { docker exec -e PGOPTIONS='-c max_parallel_workers_per_gather=0' $C psql -U postgres -X "$@"; }
Q="EXPLAIN (ANALYZE, BUFFERS) $(cat revenue.sql)"
{
psql_ -qc "DROP STATISTICS IF EXISTS charge_session_place, charge_session_vehicle" -c "ANALYZE charge_session"
echo "=== no extended statistics"; psql_ -c "$Q" >/dev/null; psql_ -c "$Q"
psql_ -qc "CREATE STATISTICS charge_session_place (ndistinct, dependencies, mcv) ON city, state FROM charge_session" \
      -c "CREATE STATISTICS charge_session_vehicle (ndistinct, dependencies, mcv) ON vehicle_make, vehicle_model, connector FROM charge_session" \
      -c "ANALYZE charge_session"
echo "=== with extended statistics"; psql_ -c "$Q" >/dev/null; psql_ -c "$Q"
} > plans.txt
