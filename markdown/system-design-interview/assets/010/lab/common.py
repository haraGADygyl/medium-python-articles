"""Shared helpers: load a stream file, name tags, connect to Redis."""
import numpy as np
import redis

MINUTES = 60


def tag(i: int) -> str:
    return f"tag{i:07d}"


def connect() -> redis.Redis:
    return redis.Redis(port=56380, decode_responses=True)


def load(seed: int) -> dict:
    z = np.load(f"stream-{seed}.npz")
    minutes = [(z[f"m{m}_ids"], z[f"m{m}_counts"]) for m in range(MINUTES)]
    hour = np.zeros(10_000_000, np.int64)

    for ids, counts in minutes:
        hour[ids] += counts

    base = np.zeros(10_000_000, np.int64)
    base[z["base_ids"]] = z["base_counts"]

    return {"minutes": minutes, "hour": hour, "base": base, "bursts": z["bursts"]}
