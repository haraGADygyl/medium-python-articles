"""Cache-aside under concurrent reprices: how many writes does a late fill undo?

    python3 race.py plain                 delete the key after COMMIT
    python3 race.py delete-first          delete the key, then UPDATE
    python3 race.py double --delay 0.5    delete after COMMIT, again 500 ms later
    python3 race.py versioned             delete after COMMIT, fills set-if-newer
    python3 race.py tombstone             writer leaves a versioned tombstone,
                                          fills set-if-newer

Readers: GET; on a miss SELECT the fare and its version, then SET it with a
TTL. A small share of fills stall between the SELECT and the SET (GC pause,
CPU throttling, a slow hop), injected with --stall-p and a lognormal length.

A cache entry is "stale" when it holds a version older than one that committed
more than GRACE seconds ago: the delete for that write has long happened, and
something put the old fare back.
"""
import argparse
import collections
import math
import random
import statistics
import threading
import time

import psycopg
import redis

PG = "host=127.0.0.1 port=55451 user=postgres password=lab dbname=postgres"
RHOST, RPORT = "127.0.0.1", 56451
GRACE = 1.0

SET_IF_NEWER = """
local cur = redis.call('GET', KEYS[1])
if cur then
  local sep = string.find(cur, '|', 1, true)
  local cached = tonumber(string.sub(cur, 1, sep - 1))
  local incoming = tonumber(ARGV[1])
  if cached > incoming then return 0 end
  if cached == incoming then
    if string.sub(cur, sep + 1) ~= '-' or ARGV[2] == '-' then return 2 end
  end
end
redis.call('SET', KEYS[1], ARGV[1] .. '|' .. ARGV[2], 'EX', ARGV[3])
return 1
"""


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0

    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))

    return ordered[k]


class Lab:
    def __init__(self, args: argparse.Namespace) -> None:
        self.a = args
        self.stop_writers = threading.Event()
        self.stop_readers = threading.Event()
        # per key: recent (version, monotonic commit time), appended by writers
        self.history: list[collections.deque] = [
            collections.deque(maxlen=16) for _ in range(args.keys)]
        self.lock = threading.Lock()
        self.c = collections.Counter()
        self.stalls: list[float] = []
        self.open_episodes: dict[int, float] = {}   # key -> start
        self.episodes: list[float] = []             # closed, seconds stale
        self.second_deletes: collections.deque = collections.deque()
        self.t0 = time.monotonic()
        # stale = still there a second after the writer's LAST invalidation
        self.grace = GRACE + (args.delay if args.mode == "double" else 0.0)

    # ---------------------------------------------------------------- setup
    def reset(self) -> None:
        with psycopg.connect(PG, autocommit=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS fares (
                sailing_id int PRIMARY KEY,
                fare_cents int NOT NULL,
                version bigint NOT NULL DEFAULT 1,
                updated_at timestamptz NOT NULL DEFAULT now())""")
            db.execute("TRUNCATE fares")
            db.execute("""INSERT INTO fares (sailing_id, fare_cents)
                SELECT g, 4900 + (g * 37) %% 9000
                FROM generate_series(0, %s - 1) g""", (self.a.keys,))
            db.execute("VACUUM ANALYZE fares")
        redis.Redis(host=RHOST, port=RPORT).flushall()

    # ------------------------------------------------------------ the model
    def settled(self, key: int, now: float) -> int:
        """Newest version committed more than self.grace seconds ago."""
        best = 0

        for version, t in list(self.history[key]):
            if t <= now - self.grace and version > best:
                best = version

        return best

    def first_newer(self, key: int, cached: int) -> float | None:
        """Commit time of the first write after the cached version."""
        times = [t for v, t in list(self.history[key]) if v > cached]

        return min(times) if times else None

    # -------------------------------------------------------------- readers
    def reader(self, seed: int) -> None:
        rnd = random.Random(seed)
        r = redis.Redis(host=RHOST, port=RPORT)
        fill = r.register_script(SET_IF_NEWER)
        db = psycopg.connect(PG, autocommit=True)
        versioned = self.a.mode in ("versioned", "tombstone")
        c = collections.Counter()
        stalls = []

        while not self.stop_readers.is_set():
            key = rnd.randrange(self.a.keys)
            raw = r.get(f"fare:{key}")
            c["reads"] += 1

            if raw is not None and not raw.endswith(b"|-"):
                c["hits"] += 1
                cached = int(raw.split(b"|", 1)[0])

                if cached < self.settled(key, time.monotonic()):
                    c["stale_reads"] += 1

                continue

            c["misses"] += 1
            fare, version = db.execute(
                "SELECT fare_cents, version FROM fares WHERE sailing_id = %s",
                (key,)).fetchone()

            if rnd.random() < self.a.stall_p:
                pause = min(self.a.stall_cap,
                            rnd.lognormvariate(math.log(self.a.stall_median),
                                               self.a.stall_sigma))
                stalls.append(pause)
                time.sleep(pause)

            if versioned:
                took = fill(keys=[f"fare:{key}"],
                            args=[version, fare, self.a.ttl])
                c["fills"] += 1
                c["fills_rejected"] += 1 if took == 0 else 0
                c["fills_same"] += 1 if took == 2 else 0
            else:
                r.set(f"fare:{key}", f"{version}|{fare}", ex=self.a.ttl)
                c["fills"] += 1

        with self.lock:
            self.c.update(c)
            self.stalls.extend(stalls)

    # -------------------------------------------------------------- writers
    def writer(self, seed: int) -> None:
        rnd = random.Random(seed)
        r = redis.Redis(host=RHOST, port=RPORT)
        tomb = r.register_script(SET_IF_NEWER)
        db = psycopg.connect(PG, autocommit=True)
        interval = self.a.writers / self.a.write_rate
        next_at = time.monotonic()
        writes = 0
        mode = self.a.mode

        while not self.stop_writers.is_set():
            key = rnd.randrange(self.a.keys)
            new_fare = rnd.randrange(3900, 18900)

            if mode == "delete-first":
                r.delete(f"fare:{key}")

            version = db.execute(
                "UPDATE fares SET fare_cents = %s, version = version + 1,"
                " updated_at = now() WHERE sailing_id = %s RETURNING version",
                (new_fare, key)).fetchone()[0]
            self.history[key].append((version, time.monotonic()))

            if mode in ("plain", "versioned"):
                r.delete(f"fare:{key}")
            elif mode == "double":
                r.delete(f"fare:{key}")
                self.second_deletes.append(
                    (time.monotonic() + self.a.delay, key))
            elif mode == "tombstone":
                tomb(keys=[f"fare:{key}"], args=[version, "-", self.a.ttl])

            writes += 1
            next_at += interval
            time.sleep(max(0.0, next_at - time.monotonic()))

        with self.lock:
            self.c["writes"] += writes

    def second_deleter(self) -> None:
        r = redis.Redis(host=RHOST, port=RPORT)

        while not self.stop_readers.is_set():
            while self.second_deletes and \
                    self.second_deletes[0][0] <= time.monotonic():
                _, key = self.second_deletes.popleft()
                r.delete(f"fare:{key}")
                self.c["second_deletes"] += 1

            time.sleep(0.005)

    # -------------------------------------------------------------- checker
    def checker(self) -> None:
        """Every 100 ms, compare every cached version with the model."""
        r = redis.Redis(host=RHOST, port=RPORT)
        names = [f"fare:{k}" for k in range(self.a.keys)]

        while not self.stop_readers.is_set():
            now = time.monotonic()
            values = r.mget(names)

            for key, raw in enumerate(values):
                stale = False

                if raw is not None and not raw.endswith(b"|-"):
                    cached = int(raw.split(b"|", 1)[0])
                    stale = cached < self.settled(key, now)

                if stale and key not in self.open_episodes:
                    start = self.first_newer(key, cached) or now
                    self.open_episodes[key] = start
                elif not stale and key in self.open_episodes:
                    self.episodes.append(now - self.open_episodes.pop(key))

            time.sleep(0.1)

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        self.reset()
        a = self.a
        threads = [threading.Thread(target=self.reader, args=(1000 + i,))
                   for i in range(a.readers)]
        writers = [threading.Thread(target=self.writer, args=(2000 + i,))
                   for i in range(a.writers)]
        helpers = [threading.Thread(target=self.checker)]

        if a.mode == "double":
            helpers.append(threading.Thread(target=self.second_deleter))

        for t in threads + helpers:
            t.start()

        time.sleep(2)   # warm the cache before the first reprice
        for t in writers:
            t.start()

        time.sleep(a.seconds)
        self.stop_writers.set()

        for t in writers:
            t.join()

        time.sleep(a.stall_cap + self.grace + 1)   # let every stalled fill land
        self.stop_readers.set()
        self.elapsed = time.monotonic() - self.t0

        for t in threads + helpers:
            t.join()

        self.report()

    def report(self) -> None:
        a, c = self.a, self.c
        r = redis.Redis(host=RHOST, port=RPORT)

        with psycopg.connect(PG, autocommit=True) as db:
            rows = db.execute(
                "SELECT sailing_id, version, fare_cents FROM fares").fetchall()

        stuck, ttls, wrong_cents = [], [], []

        for key, version, fare in rows:
            raw = r.get(f"fare:{key}")

            if raw is None or raw.endswith(b"|-"):
                continue

            cached_v, cached_fare = raw.decode().split("|")

            if int(cached_v) < version:
                stuck.append(key)
                ttls.append(r.ttl(f"fare:{key}"))
                wrong_cents.append(abs(int(cached_fare) - fare))

        still_open = len(self.open_episodes)
        undone = len(self.episodes) + still_open
        label = a.mode + (f" {int(a.delay * 1000)} ms" if a.mode == "double"
                          else "")
        print(f"mode {label}: {a.keys:,} sailings, {a.readers} readers, "
              f"{a.write_rate} reprices/s for {a.seconds} s")
        print(f"  stalls injected: {len(self.stalls):,} fills "
              f"({a.stall_p:.0%} of misses), p50 "
              f"{statistics.median(self.stalls) * 1000 if self.stalls else 0:.0f}"
              f" ms, max {max(self.stalls, default=0) * 1000:.0f} ms")
        print(f"  reads {c['reads']:,}, hit ratio "
              f"{c['hits'] / max(1, c['reads']):.1%}, misses {c['misses']:,} "
              f"({c['misses'] / self.elapsed:,.0f}/s"
              f" to Postgres)")
        print(f"  reprices: {c['writes']:,}"
              + (f", second deletes {c['second_deletes']:,}"
                 if a.mode == "double" else "")
              + (f", fills refused as older {c['fills_rejected']:,}"
                 f", already there {c['fills_same']:,}"
                 if a.mode in ("versioned", "tombstone") else ""))
        print(f"  stale reads (older than a reprice > {self.grace:g} s old): "
              f"{c['stale_reads']:,} ({c['stale_reads'] / max(1, c['hits']):.3%}"
              f" of hits)")
        print(f"  reprices undone by a late fill: {undone:,} "
              f"({undone / max(1, c['writes']):.2%})")

        if self.episodes:
            print(f"    fixed by a later reprice: {len(self.episodes):,}, "
                  f"stale p50 {statistics.median(self.episodes):.2f} s, "
                  f"max {max(self.episodes):.2f} s")

        print(f"  still stale {a.stall_cap + self.grace + 1:.0f} s after the last "
              f"reprice: {len(stuck)} sailings"
              + (f", TTL left {min(ttls)}-{max(ttls)} s, wrong by "
                 f"{statistics.median(wrong_cents) / 100:.2f} EUR median"
                 if stuck else ""))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["plain", "delete-first", "double",
                                    "versioned", "tombstone"])
    p.add_argument("--delay", type=float, default=0.5)
    p.add_argument("--keys", type=int, default=1000)
    p.add_argument("--readers", type=int, default=32)
    p.add_argument("--writers", type=int, default=8)
    p.add_argument("--write-rate", type=int, default=400)
    p.add_argument("--seconds", type=int, default=60)
    p.add_argument("--ttl", type=int, default=3600)
    p.add_argument("--stall-p", type=float, default=0.02)
    p.add_argument("--stall-median", type=float, default=0.2)
    p.add_argument("--stall-sigma", type=float, default=1.0)
    p.add_argument("--stall-cap", type=float, default=4.0)
    Lab(p.parse_args()).run()


if __name__ == "__main__":
    main()
