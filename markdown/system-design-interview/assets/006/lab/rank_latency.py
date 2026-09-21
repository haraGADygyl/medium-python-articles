"""Rank for one player: Postgres three ways against a Redis sorted set."""
import random
import statistics
import time

import psycopg
import redis

DSN = "host=127.0.0.1 port=5462 dbname=postgres user=postgres password=demo"
KEY = "leaderboard:global"
WINDOW_SAMPLES = int(__import__("os").environ.get("WINDOW_SAMPLES", 20))
PLAYERS = 50_000_000
SAMPLES = int(__import__("os").environ.get("SAMPLES", 200))

COUNT_ABOVE = """
SELECT count(*) + 1 FROM player_score
WHERE score > (SELECT score FROM player_score WHERE player_id = %s)
"""
WINDOW_RANK = """
SELECT rank FROM (
    SELECT player_id, rank() OVER (ORDER BY score DESC) AS rank
    FROM player_score
) ranked WHERE player_id = %s
"""


def timed(fn, ids: list[int]) -> dict:
    """Run fn once per id, in milliseconds."""
    lat = []
    for player_id in ids:
        started = time.perf_counter()
        fn(player_id)
        lat.append((time.perf_counter() - started) * 1000)
    lat.sort()
    return {"p50_ms": round(statistics.median(lat), 2),
            "p99_ms": round(lat[int(len(lat) * 0.99)], 2),
            "max_ms": round(lat[-1], 2),
            "calls": len(lat)}


def main() -> None:
    rng = random.Random(20260921)
    ids = [rng.randrange(1, PLAYERS + 1) for _ in range(SAMPLES)]
    pool = redis.Redis(host="127.0.0.1", port=6389, decode_responses=True)
    with psycopg.connect(DSN, autocommit=True) as conn:
        def sql_count(player_id: int) -> None:
            conn.execute(COUNT_ABOVE, (player_id,)).fetchone()

        def sql_window(player_id: int) -> None:
            conn.execute(WINDOW_RANK, (player_id,)).fetchone()

        def zrevrank(player_id: int) -> None:
            pool.zrevrank(KEY, f"p{player_id}")

        rows = [
            ("postgres count(*) above", timed(sql_count, ids)),
            ("postgres rank() window", timed(sql_window, ids[:WINDOW_SAMPLES])),
            ("redis ZREVRANK", timed(zrevrank, ids)),
        ]
        plan = conn.execute(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + COUNT_ABOVE,
            (ids[0],)).fetchall()
    print(f"rank of one player among {PLAYERS:,}, {SAMPLES} random players")
    print(f"{'method':<26}{'p50 ms':>10}{'p99 ms':>10}{'max ms':>10}"
          f"{'calls':>8}")
    for label, row in rows:
        print(f"{label:<26}{row['p50_ms']:>10}{row['p99_ms']:>10}"
              f"{row['max_ms']:>10}{row['calls']:>8}")
    print()
    print("EXPLAIN ANALYZE for the count(*) form:")
    for line in plan:
        print("  " + line[0])


if __name__ == "__main__":
    main()
