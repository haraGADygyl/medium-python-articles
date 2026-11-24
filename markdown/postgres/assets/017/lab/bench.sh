#!/usr/bin/env bash
# Steady-state single-row inserts into one table: pgbench after a CHECKPOINT,
# with WAL, full-page images and primary-key block reads taken as deltas.
#
#   ./bench.sh v4 [clients] [seconds]     uses insert_v4.sql against delivery_v4
set -euo pipefail
cd "$(dirname "$0")"
t="$1"; clients="${2:-8}"; secs="${3:-60}"
PSQL=(docker exec -i pg18-uuid psql -U postgres -XAtq)

snap() {   # counters only; pgstatindex would count its own full-index read as pkey reads
  "${PSQL[@]}" -F' ' -c "
    SELECT w.wal_records, w.wal_fpi, w.wal_bytes,
           i.idx_blks_read, i.idx_blks_hit,
           c.num_timed + c.num_requested,
           (SELECT count(*) FROM delivery_$t)
    FROM pg_stat_wal w, pg_statio_user_indexes i, pg_stat_checkpointer c
    WHERE i.indexrelname = 'delivery_${t}_pkey'"
}

leaf() {   # leaf pages and density, taken outside the counter window
  "${PSQL[@]}" -F' ' -c "SELECT leaf_pages, avg_leaf_density FROM pgstatindex('delivery_${t}_pkey')"
}

docker cp "insert_$t.sql" pg18-uuid:/insert.sql
"${PSQL[@]}" -c "CHECKPOINT"
read -r leaf0 dens0 < <(leaf)
sleep 1
read -r rec0 fpi0 bytes0 rd0 hit0 ck0 rows0 < <(snap)
docker exec pg18-uuid pgbench -U postgres -n -M prepared -c "$clients" -j 4 -T "$secs" -P 10 \
  -f /insert.sql postgres 2>&1 | grep -E '^(progress|number of transactions actually|latency average|tps)'
sleep 2
read -r rec1 fpi1 bytes1 rd1 hit1 ck1 rows1 < <(snap)
read -r leaf1 dens1 < <(leaf)

tx=$((rows1 - rows0))
awk -v tx="$tx" -v rec=$((rec1 - rec0)) -v fpi=$((fpi1 - fpi0)) -v b=$((bytes1 - bytes0)) \
    -v rd=$((rd1 - rd0)) -v hit=$((hit1 - hit0)) -v ck=$((ck1 - ck0)) \
    -v leaf=$((leaf1 - leaf0)) -v d0="$dens0" -v d1="$dens1" -v t="$t" 'BEGIN {
  printf "%s: %d rows, WAL %.0f MB (%.0f bytes/row), FPI %d (%.2f/row), records %.2f/row\n",
         t, tx, b/1048576, b/tx, fpi, fpi/tx, rec/tx
  printf "%s: pkey blocks read %d, hit %d (%.1f%% hit), checkpoints %d\n",
         t, rd, hit, 100*hit/(hit+rd), ck
  printf "%s: leaf pages +%d (%.0f rows per new leaf), density %.2f%% -> %.2f%%\n",
         t, leaf, (leaf > 0 ? tx/leaf : 0), d0, d1
}'
