"""Bulk-load each delivery table in 1M-row chunks; record time, WAL and buffers per chunk.

Usage: python3 load.py [rows_millions]   -> load.txt
"""

import json
import sys

import psycopg

DSN = "host=localhost port=55421 user=postgres password=lab dbname=postgres"
TABLES = ["delivery_serial", "delivery_v4", "delivery_v7"]
CHUNK = 1_000_000

INSERT = """
INSERT INTO {table} (endpoint_id, status_code, payload_bytes, attempted_at)
SELECT 1 + (random() * 4999)::int,
       (ARRAY[200, 200, 200, 202, 204, 400, 410, 500, 503])[1 + (random() * 8)::int],
       200 + (random() * 9800)::int,
       now()
FROM generate_series(1, {rows})
"""


def chunk_stats(cur: psycopg.Cursor, table: str) -> dict[str, float]:
    """Run one chunk under EXPLAIN (ANALYZE, BUFFERS, WAL) and pull out the totals."""
    sql = INSERT.format(table=table, rows=CHUNK)
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, WAL, FORMAT JSON) {sql}")
    report = cur.fetchone()[0][0]
    plan = report["Plan"]

    return {
        "ms": report["Execution Time"],
        "wal_mb": plan["WAL Bytes"] / 1024 / 1024,
        "fpi": plan["WAL FPI"],
        "hit": plan["Shared Hit Blocks"],
        "read": plan["Shared Read Blocks"],
        "written": plan["Shared Written Blocks"],
    }


def checkpoints(cur: psycopg.Cursor) -> int:
    """Checkpoints completed so far (timed + requested)."""
    cur.execute("SELECT num_timed + num_requested FROM pg_stat_checkpointer")

    return cur.fetchone()[0]


def main() -> None:
    millions = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        for table in TABLES:
            cur.execute("CHECKPOINT")
            start_ckpt = checkpoints(cur)
            totals = {"ms": 0.0, "wal_mb": 0.0, "fpi": 0}
            print(f"\n== {table}")
            print(" chunk  rows_M      ms   wal_MB      fpi     hit    read  written")

            for n in range(1, millions + 1):
                stats = chunk_stats(cur, table)

                for key in totals:
                    totals[key] += stats[key]

                print(f"{n:6d} {n:7d} {stats['ms']:7.0f} {stats['wal_mb']:8.1f} "
                      f"{stats['fpi']:8d} {stats['hit']:7d} {stats['read']:7d} "
                      f"{stats['written']:8d}", flush=True)

            cur.execute("VACUUM ANALYZE " + table)
            cur.execute(f"""
                SELECT pg_size_pretty(pg_table_size('{table}')),
                       pg_size_pretty(pg_relation_size('{table}_pkey')),
                       s.leaf_pages, s.avg_leaf_density
                FROM pgstatindex('{table}_pkey') AS s
            """)
            heap, index, leaves, density = cur.fetchone()
            print(f"total: {totals['ms'] / 1000:.1f} s, WAL {totals['wal_mb']:.0f} MB, "
                  f"FPI {totals['fpi']}, checkpoints {checkpoints(cur) - start_ckpt}")
            print(f"heap {heap}, pkey {index}, leaf pages {leaves}, "
                  f"avg leaf density {density}%")


if __name__ == "__main__":
    main()
