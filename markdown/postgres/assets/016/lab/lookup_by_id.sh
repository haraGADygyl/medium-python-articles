#!/usr/bin/env bash
# Point lookup by scan_id (no partition key in the WHERE): unpartitioned vs 19 monthly partitions.
# One client, 20,000 lookups each, warmed first.
set -euo pipefail
C=pg18-partition
for t in parcel_scan parcel_scan_monthly; do
  docker exec $C bash -c "printf '\\\\set id random(1, 20000000)\nSELECT * FROM $t WHERE scan_id = :id;\n' > /tmp/byid_$t.sql"
  docker exec $C pgbench -U postgres -n -f /tmp/byid_$t.sql -t 20000 monthly >/dev/null 2>&1
  echo "== $t"; docker exec $C pgbench -U postgres -n -f /tmp/byid_$t.sql -t 20000 monthly 2>/dev/null | grep -E 'latency average|^tps'
  echo "== $t, with the key range"
  docker exec $C bash -c "printf '\\\\set id random(1, 20000000)\nSELECT * FROM $t WHERE scan_id = :id AND scanned_at >= now() - interval %s;\n' \"'7 days'\" > /tmp/byidk_$t.sql"
  docker exec $C pgbench -U postgres -n -f /tmp/byidk_$t.sql -t 20000 monthly 2>/dev/null | grep -E 'latency average'
done
echo "== parcel_scan_monthly, constant key range (plan-time pruning)"
docker exec $C bash -c "printf '\\\\set id random(1, 20000000)\nSELECT * FROM parcel_scan_monthly WHERE scan_id = :id AND scanned_at >= %s;\n' \"'2026-11-16 00:00+00'\" > /tmp/byidc.sql"
docker exec $C pgbench -U postgres -n -f /tmp/byidc.sql -t 20000 monthly 2>/dev/null | grep -E 'latency average'
echo "== parcel_scan_monthly, now() key range, prepared statements (-M prepared)"
docker exec $C pgbench -U postgres -n -M prepared -f /tmp/byidk_parcel_scan_monthly.sql -t 20000 monthly 2>/dev/null | grep -E 'latency average'
echo "== parcel_scan_monthly, no key, prepared statements (-M prepared)"
docker exec $C pgbench -U postgres -n -M prepared -f /tmp/byid_parcel_scan_monthly.sql -t 20000 monthly 2>/dev/null | grep -E 'latency average'
echo "== parcel_scan, no key, prepared statements (-M prepared)"
docker exec $C pgbench -U postgres -n -M prepared -f /tmp/byid_parcel_scan.sql -t 20000 monthly 2>/dev/null | grep -E 'latency average'
