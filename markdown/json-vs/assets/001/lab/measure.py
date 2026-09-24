"""json vs jsonb in PostgreSQL, on the shared buoy payload.

Needs a scratch PostgreSQL; run.sh starts one. Override with LAB_DSN.
"""
import json
import os
import sys
import time
from pathlib import Path

import psycopg

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

DSN = os.environ.get("LAB_DSN",
                     "postgresql://postgres:lab@127.0.0.1:55001/postgres")
RUNS = 5
RECORDS = 50000

QUERIES = {
    "count failed QC":
        "SELECT count(*) FROM {t} WHERE (doc->>'qc_passed')::boolean = false",
    "avg wave height per buoy":
        "SELECT doc->>'buoy_id', "
        "round(avg((doc->>'wave_height_m')::numeric), 3) "
        "FROM {t} GROUP BY 1 ORDER BY 1",
    "sensors, the last key":
        "SELECT sum({f}_array_length(doc->'sensors')) FROM {t}",
    "NE-08 and failed QC":
        "SELECT count(*) FROM {t} WHERE doc->>'buoy_id' = 'NE-08' "
        "AND (doc->>'qc_passed')::boolean = false",
    "whole document as text":
        "SELECT sum(length(doc::text)) FROM {t}",
}
CONTAINS = """SELECT count(*) FROM obs_jsonb
              WHERE doc @> '{"buoy_id": "NE-08", "qc_passed": false}'"""


def best_ms(cur: psycopg.Cursor, sql: str) -> tuple[float, object]:
    """Fastest of RUNS executions after one warm-up, plus the first cell."""
    cur.execute(sql)
    result = cur.fetchall()[0][-1]
    fastest = float("inf")
    for _ in range(RUNS):
        started = time.perf_counter()
        cur.execute(sql)
        cur.fetchall()
        fastest = min(fastest, (time.perf_counter() - started) * 1000)
    return fastest, result


def main() -> None:
    lines = [json.dumps(row, separators=(",", ":")) for row in build(RECORDS)]
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()
        version = cur.execute("SHOW server_version").fetchone()[0]
        cur.execute("SET max_parallel_workers_per_gather = 0")
        cur.execute("DROP TABLE IF EXISTS raw, obs_json, obs_jsonb")
        cur.execute("CREATE TABLE raw (line text NOT NULL)")
        cur.execute("CREATE TABLE obs_json (doc json NOT NULL)")
        cur.execute("CREATE TABLE obs_jsonb (doc jsonb NOT NULL)")
        with cur.copy("COPY raw (line) FROM STDIN") as copy:
            for line in lines:
                copy.write_row((line,))

        print(f"PostgreSQL {version}, {RECORDS} buoy records, best of {RUNS}, "
              f"parallel query off")
        print()
        print("load: INSERT ... SELECT line::<type> FROM raw")
        for table, kind in (("obs_json", "json"), ("obs_jsonb", "jsonb")):
            fastest = float("inf")
            for _ in range(RUNS):
                cur.execute(f"TRUNCATE {table}")
                started = time.perf_counter()
                cur.execute(f"INSERT INTO {table} SELECT line::{kind} FROM raw")
                fastest = min(fastest, (time.perf_counter() - started) * 1000)
            print(f"  {kind:<6}{fastest:>9.1f} ms")
        cur.execute("VACUUM ANALYZE raw, obs_json, obs_jsonb")

        print()
        print(f"{'storage':<12}{'table bytes':>14}{'avg doc bytes':>15}")
        for table in ("raw", "obs_json", "obs_jsonb"):
            column = "line" if table == "raw" else "doc"
            size, avg = cur.execute(
                f"SELECT pg_total_relation_size('{table}'), "
                f"avg(pg_column_size({column}))::int FROM {table}").fetchone()
            print(f"{table:<12}{size:>14,}{avg:>15,}")

        print()
        print(f"{'query':<26}{'json ms':>10}{'jsonb ms':>10}   result")
        for label, template in QUERIES.items():
            json_ms, result = best_ms(cur, template.format(t="obs_json",
                                                           f="json"))
            jsonb_ms, check = best_ms(cur, template.format(t="obs_jsonb",
                                                           f="jsonb"))
            same = "" if result == check else f"  (jsonb: {check})"
            print(f"{label:<26}{json_ms:>10.1f}{jsonb_ms:>10.1f}   "
                  f"{result}{same}")

        print()
        print("containment, jsonb only: doc @> '{\"buoy_id\": \"NE-08\", "
              "\"qc_passed\": false}'")
        seq_ms, found = best_ms(cur, CONTAINS)
        print(f"  seq scan                 {seq_ms:>9.1f} ms   {found}")
        for opclass in ("jsonb_ops", "jsonb_path_ops"):
            cur.execute("DROP INDEX IF EXISTS obs_jsonb_gin")
            started = time.perf_counter()
            cur.execute(f"CREATE INDEX obs_jsonb_gin ON obs_jsonb "
                        f"USING gin (doc {opclass})")
            built = (time.perf_counter() - started) * 1000
            cur.execute("ANALYZE obs_jsonb")
            size = cur.execute(
                "SELECT pg_relation_size('obs_jsonb_gin')").fetchone()[0]
            gin_ms, found = best_ms(cur, CONTAINS)
            plan = cur.execute("EXPLAIN " + CONTAINS).fetchall()
            uses = any("obs_jsonb_gin" in row[0] for row in plan)
            print(f"  gin {opclass:<21}{gin_ms:>9.1f} ms   {found}   "
                  f"index {size:,} bytes, built in {built:.0f} ms, "
                  f"used: {uses}")

        print()
        print("expression index on doc->>'buoy_id', works for both types")
        for table in ("obs_json", "obs_jsonb"):
            cur.execute(f"CREATE INDEX {table}_buoy ON {table} "
                        f"((doc->>'buoy_id'))")
            cur.execute(f"ANALYZE {table}")
            sql = QUERIES["NE-08 and failed QC"].format(t=table)
            idx_ms, found = best_ms(cur, sql)
            plan = cur.execute("EXPLAIN " + sql).fetchall()
            uses = any(f"{table}_buoy" in row[0] for row in plan)
            print(f"  {table:<24}{idx_ms:>9.1f} ms   {found}   used: {uses}")

        print()
        try:
            cur.execute("SELECT count(*) FROM obs_json "
                        "WHERE doc @> '{\"buoy_id\": \"NE-08\"}'")
        except psycopg.Error as exc:
            print(f"json @>: {type(exc).__name__}: "
                  f"{str(exc).splitlines()[0]}")
        cur.execute("DROP TABLE raw, obs_json, obs_jsonb")


if __name__ == "__main__":
    main()
