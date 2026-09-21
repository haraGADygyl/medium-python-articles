"""Competition rank in Redis: count the scores strictly above you."""
import random
import statistics
import time

import redis

KEY = "leaderboard:global"
SAMPLES = 200


def main() -> None:
    pool = redis.Redis(host="127.0.0.1", port=6389, decode_responses=True)
    rng = random.Random(20260921)
    members = [f"p{rng.randrange(1, 50_000_000)}" for _ in range(SAMPLES)]

    ordinal, competition = [], []
    for member in members:
        started = time.perf_counter()
        pool.zrevrank(KEY, member)
        ordinal.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        score = pool.zscore(KEY, member)
        pool.zcount(KEY, f"({score}", "+inf")
        competition.append((time.perf_counter() - started) * 1000)

    for label, lat in (("ZREVRANK (ordinal)", ordinal),
                       ("ZSCORE + ZCOUNT (competition)", competition)):
        lat.sort()
        print(f"{label:<32}p50 {statistics.median(lat):>6.2f} ms   "
              f"p99 {lat[int(len(lat) * 0.99)]:>6.2f} ms")

    top = pool.zrevrange(KEY, 0, 0, withscores=True)[0][1]
    tied = pool.zrangebyscore(KEY, top, top)
    print()
    print(f"the {len(tied)} players on score {int(top):,}:")
    for member in sorted(tied)[:3]:
        score = pool.zscore(KEY, member)
        print(f"  {member:<12} ZREVRANK {pool.zrevrank(KEY, member):>4}   "
              f"ZCOUNT above {pool.zcount(KEY, f'({score}', '+inf'):>4}")


if __name__ == "__main__":
    main()
