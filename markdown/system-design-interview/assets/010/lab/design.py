"""The code blocks the article shows, in order, as one importable module.

verify_design.py drives every function here against the lab's Redis state.
"""
import redis

r = redis.Redis(decode_responses=True)


def record(tag: str, now: float) -> None:
    """One ZINCRBY per use, into the bucket for the current minute."""
    key = f"trend:min:{int(now // 60)}"
    r.zincrby(key, 1, tag)
    r.expire(key, 3_900)


def trending_now(now: float) -> list[tuple[str, float]]:
    """Union the last 60 minutes and read the top 10."""
    minute = int(now // 60)
    keys = [f"trend:min:{m}" for m in range(minute - 59, minute + 1)]
    r.zunionstore("trend:hour", keys)

    return r.zrevrange("trend:hour", 0, 9, withscores=True)


ERROR, PROB, KEEP = 0.001, 0.01, 200


def record_batch(minute: int, counts: dict[str, int]) -> None:
    """Add a batch of uses to the minute's sketch; keep its 200 biggest."""
    key, cand = f"trend:cms:{minute}", f"trend:cand:{minute}"

    try:
        r.execute_command("CMS.INITBYPROB", key, ERROR, PROB)
    except redis.ResponseError:
        pass  # this minute's sketch already exists

    flat = [x for pair in counts.items() for x in pair]
    estimates = r.execute_command("CMS.INCRBY", key, *flat)
    r.zadd(cand, dict(zip(counts, estimates)), gt=True)
    r.zremrangebyrank(cand, 0, -(KEEP + 1))


def top_tags(minute: int) -> list[tuple[str, int]]:
    """Merge the hour's sketches, score the candidates, keep 10."""
    minutes = range(minute - 59, minute + 1)
    keys = [f"trend:cms:{m}" for m in minutes]
    r.delete("trend:cms:hour")
    r.execute_command("CMS.INITBYPROB", "trend:cms:hour", ERROR, PROB)
    r.execute_command("CMS.MERGE", "trend:cms:hour", len(keys), *keys)
    r.zunionstore("trend:cand:hour", [f"trend:cand:{m}" for m in minutes])
    names = r.zrange("trend:cand:hour", 0, -1)
    counts = r.execute_command("CMS.QUERY", "trend:cms:hour", *names)

    return sorted(zip(names, counts), key=lambda x: -x[1])[:10]


MIN_USES, MIN_LIFT, SMOOTH = 500, 5.0, 10


def is_trending(this_hour: int, last_24h: int) -> tuple[bool, float]:
    """At least 500 uses, and five times the usual hourly rate."""
    lift = (this_hour + SMOOTH) / (last_24h / 24 + SMOOTH)

    return this_hour >= MIN_USES and lift >= MIN_LIFT, lift


WIDTH, DEPTH = 50_000, 7


def merged(dest: str, keys: list[str]) -> None:
    """Rebuild dest as the sum of keys; all share width and depth."""
    r.delete(dest)
    r.execute_command("CMS.INITBYDIM", dest, WIDTH, DEPTH)
    r.execute_command("CMS.MERGE", dest, len(keys), *keys)


def trending_panel(bucket: int, hour: int) -> list[tuple[str, float]]:
    """12 five-minute buckets against 24 hourly baseline sketches."""
    buckets = range(bucket - 11, bucket + 1)
    merged("trend:hour", [f"trend:cms:{b}" for b in buckets])
    merged("trend:day", [f"trend:base:{h}" for h in range(hour - 24, hour)])
    names = list({n for b in buckets
                  for n in r.zrange(f"trend:cand:{b}", 0, -1)})
    now = r.execute_command("CMS.QUERY", "trend:hour", *names)
    day = r.execute_command("CMS.QUERY", "trend:day", *names)
    rows = []

    for name, uses, baseline in zip(names, now, day):
        ok, lift = is_trending(uses, baseline)

        if ok:
            rows.append((name, lift))

    return sorted(rows, key=lambda x: -x[1])
