"""Load the same scores into a Redis sorted set, in pipelined batches."""
import sys
import time

import redis

POOL = redis.Redis(host="127.0.0.1", port=6389, decode_responses=True)
KEY = "leaderboard:global"
BATCH = 50000


def main() -> None:
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 50_000_000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    import random
    rng = random.Random(20260921 + seed)
    started = time.monotonic()
    for start in range(1, total + 1, BATCH):
        pipe = POOL.pipeline(transaction=False)
        mapping = {f"p{i}": rng.randrange(0, 250001)
                   for i in range(start, min(start + BATCH, total + 1))}
        pipe.zadd(KEY, mapping)
        pipe.execute()
        if start % 5_000_000 == 1:
            used = POOL.info("memory")["used_memory_human"]
            print(f"{start - 1:>10,} members  {used:>9}  "
                  f"{time.monotonic() - started:6.1f}s", flush=True)
    print(f"done: {POOL.zcard(KEY):,} members, "
          f"{POOL.info('memory')['used_memory_human']}, "
          f"{time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main()
