"""Paging the top of a leaderboard while scores are still moving."""
import random
import threading
import time

import redis

KEY = "leaderboard:global"
PAGE = 100
PAGES = 100                      # 100 pages x 100 = the top 10000
WRITES_PER_SECOND = 2000
TOP_BAND = (249_900, 250_000)    # scores that land inside the top 10000


def pool() -> redis.Redis:
    return redis.Redis(host="127.0.0.1", port=6389, decode_responses=True)


def churn(stop: threading.Event, moved: list[str]) -> None:
    """Half the writes climb into the paged region, half drop out of it.

    Climbers push everyone below them down a rank, which makes offset paging
    show a player twice. Players dropping out pull everyone up, which makes
    offset paging skip a player entirely.
    """
    conn, rng = pool(), random.Random(7)
    while not stop.is_set():
        start = rng.randrange(0, 9000)
        leaving = conn.zrevrange(KEY, start, start + 400)
        pipe = conn.pipeline(transaction=False)
        for index in range(100):
            if index % 2 == 0:
                member = f"p{rng.randrange(1, 50_000_000)}"
                pipe.zadd(KEY, {member: rng.randrange(*TOP_BAND)})
            elif leaving:
                member = leaving[rng.randrange(0, len(leaving))]
                pipe.zadd(KEY, {member: rng.randrange(0, 200_000)})
            moved.append(member)
        pipe.execute()
        time.sleep(100 / WRITES_PER_SECOND)


def page_by_offset(conn: redis.Redis) -> list[str]:
    """The obvious paging: ZREVRANGE with an offset per page."""
    seen: list[str] = []
    for page in range(PAGES):
        start = page * PAGE
        seen.extend(conn.zrevrange(KEY, start, start + PAGE - 1))
        time.sleep(0.01)
    return seen


def page_by_cursor(conn: redis.Redis) -> list[str]:
    """Keyset paging on (score, member): the cursor is a position, not a count.

    Redis can only seek by score, so members already returned at the cursor's
    score are carried forward and skipped — a tie group of 200 needs that.
    """
    seen: list[str] = []
    cursor_score: float | str = "+inf"
    done_at_score: set[str] = set()
    for _ in range(PAGES):
        rows = conn.zrevrangebyscore(
            KEY, cursor_score, "-inf",
            start=0, num=PAGE + len(done_at_score), withscores=True)
        fresh = [(m, s) for m, s in rows if m not in done_at_score][:PAGE]
        if not fresh:
            break
        seen.extend(m for m, _ in fresh)
        last_score = fresh[-1][1]
        if last_score == cursor_score:
            done_at_score |= {m for m, s in fresh if s == last_score}
        else:
            done_at_score = {m for m, s in fresh if s == last_score}
        cursor_score = last_score
        time.sleep(0.01)
    return seen


def main() -> None:
    conn = pool()
    print(f"paging the top {PAGES * PAGE:,} in pages of {PAGE}, "
          f"{WRITES_PER_SECOND} score updates/s into the same region")
    print(f"{'method':<24}{'rows':>7}{'unique':>9}{'dupes':>7}"
          f"{'missed':>8}{'writes':>9}")
    for name, fn in (("ZREVRANGE + offset", page_by_offset),
                     ("cursor on (score, id)", page_by_cursor)):
        before = set(conn.zrevrange(KEY, 0, PAGES * PAGE - 1))
        stop, moved = threading.Event(), []
        worker = threading.Thread(target=churn, args=(stop, moved),
                                  daemon=True)
        worker.start()
        seen = fn(conn)
        stop.set()
        worker.join(timeout=2)
        after = set(conn.zrevrange(KEY, 0, PAGES * PAGE - 1))
        stable = before & after          # in the top 10000 the whole time
        print(f"{name:<24}{len(seen):>7}{len(set(seen)):>9}"
              f"{len(seen) - len(set(seen)):>7}"
              f"{len(stable - set(seen)):>8}{len(moved):>9}")
    print()
    print("'missed' counts players in the top 10000 both before and after")
    print("paging who never appeared on any page.")


if __name__ == "__main__":
    main()
