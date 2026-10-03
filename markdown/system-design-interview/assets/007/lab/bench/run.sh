#!/usr/bin/env bash
# Payment throughput: no fee leg, fee as a hot column, fee as an appended entry.
# Three rounds, configurations interleaved inside each round so slow drift on the
# host hits every configuration equally. VACUUM + CHECKPOINT before every 30 s run;
# the server runs with max_wal_size=16GB, checkpoint_timeout=30min.
# Each line reports the median of the three runs and all three runs.
set -euo pipefail
CONFIGS=("pay_nofee 1" "pay_nofee 32" "pay_hot_column 1" "pay_hot_column 8"
         "pay_hot_column 32" "pay_hot_column 64" "pay_hot_append 1" "pay_hot_append 32")
declare -A RESULTS
for round in 1 2 3; do
  for cfg in "${CONFIGS[@]}"; do
    read -r script clients <<<"$cfg"
    docker exec bal-pg psql -U postgres -qc "VACUUM account" -c CHECKPOINT
    out=$(docker exec bal-pg pgbench -U postgres -n -c "$clients" -j "$(( clients < 8 ? clients : 8 ))" \
          -T "${DUR:-30}" -r -f "/bench/$script.sql" postgres 2>&1)
    tps=$(grep -oP 'tps = \K[0-9.]+' <<<"$out")
    lat=$(grep -oP 'latency average = \K[0-9.]+' <<<"$out")
    hot=$(grep -E 'WHERE id = 0;' <<<"$out" | awk '{print $1}' || true)
    RESULTS["$cfg"]+="$tps $lat ${hot:--}"$'\n'
  done
done
for cfg in "${CONFIGS[@]}"; do
  rows=$(sort -n -k1 <<<"${RESULTS[$cfg]%$'\n'}")
  read -r tps lat hot <<<"$(sed -n 2p <<<"$rows")"
  read -r script clients <<<"$cfg"
  printf '%-15s %3s clients %7.0f tps %8s ms avg  fee-row wait %6s ms   runs: %s\n' \
    "$script" "$clients" "$tps" "$lat" "$hot" "$(awk '{printf "%.0f ", $1}' <<<"$rows")"
done
