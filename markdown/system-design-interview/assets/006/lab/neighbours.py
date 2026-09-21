"""Players near me, and what an exact page costs."""
import random
import statistics
import time

import psycopg
import redis

DSN = "host=127.0.0.1 port=5462 dbname=postgres user=postgres password=demo"
KEY = "leaderboard:global"
SNAPSHOT = "leaderboard:snapshot"
WINDOW = 5
SAMPLES = 40

NEIGHBOURS_SQL = """
SELECT player_id, score FROM player_score
ORDER BY score DESC, player_id
OFFSET %s LIMIT %s
"""


def timed(fn, args_list) -> dict:
    lat = []
    for args in args_list:
        started = time.perf_counter()
        fn(*args)
        lat.append((time.perf_counter() - started) * 1000)
    lat.sort()
    return {"p50": round(statistics.median(lat), 2),
            "p99": round(lat[int(len(lat) * 0.99)], 2)}


def main() -> None:
    rng = random.Random(20260921)
    pool = redis.Redis(host="127.0.0.1", port=6389, decode_responses=True)
    ranks = [rng.randrange(1000, 49_000_000) for _ in range(SAMPLES)]

    def redis_neighbours(rank: int) -> None:
        pool.zrevrange(KEY, max(0, rank - WINDOW), rank + WINDOW,
                       withscores=True)

    def sql_neighbours(rank: int) -> None:
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute(NEIGHBOURS_SQL,
                         (max(0, rank - WINDOW), WINDOW * 2 + 1)).fetchall()

    r = timed(redis_neighbours, [(x,) for x in ranks])
    s = timed(sql_neighbours, [(x,) for x in ranks[:8]])
    print(f"eleven rows centred on a random rank, {SAMPLES} samples")
    print(f"  redis ZREVRANGE rank-5..rank+5   p50 {r['p50']:>9} ms   "
          f"p99 {r['p99']:>9} ms")
    print(f"  postgres ORDER BY ... OFFSET n   p50 {s['p50']:>9} ms   "
          f"p99 {s['p99']:>9} ms   (8 samples)")

    print()
    before = pool.info("memory")["used_memory"]
    started = time.monotonic()
    copied = pool.zrangestore(SNAPSHOT, KEY, 0, 9999, desc=True)
    snap_ms = (time.monotonic() - started) * 1000
    after = pool.info("memory")["used_memory"]
    print(f"exact paging needs a snapshot:")
    print(f"  ZRANGESTORE top 10000           {snap_ms:.1f} ms, "
          f"{copied:,} members, +{(after - before) / 1024:.0f} KiB")
    pool.delete(SNAPSHOT)
    info = pool.info("memory")
    print(f"  whole sorted set                 {pool.zcard(KEY):,} members, "
          f"{info['used_memory'] / 1024 ** 3:.2f} GiB "
          f"({info['used_memory'] / pool.zcard(KEY):.0f} bytes/member)")


if __name__ == "__main__":
    main()
