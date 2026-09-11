"""Distributed lock expiry lab: naive / watchdog / fenced."""
import hashlib
import multiprocessing as mp
import os
import random
import signal
import sys
import threading
import time
import uuid

import psycopg2
import redis

PG = "host=127.0.0.1 port=5442 dbname=scenes user=postgres password=demo"
RURL = "redis://127.0.0.1:6399/0"

SCENES = [f"S2A-{n:04d}" for n in range(80)]
LOCK_TTL_MS = 2000
STALL_SECONDS = (2.2, 3.4)
STALL_PROBABILITY = 0.30
ARRIVAL_SECONDS = 0.45
WORK_SECONDS = (0.4, 1.2)
ROUNDS_PER_SECOND = 25000
CNT = "counters"

UNLOCK_REPORTING = """
local prev = redis.call('get', KEYS[1])
redis.call('del', KEYS[1])
return prev
"""
UNLOCK_SAFE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""
EXTEND = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""


def db():
    c = psycopg2.connect(PG)
    c.autocommit = True
    return c


def setup():
    conn = db()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS scene_product, write_log, held")
        cur.execute("""
            CREATE TABLE scene_product (
                scene_id    text PRIMARY KEY,
                checksum    text NOT NULL,
                written_by  text NOT NULL,
                fence_token bigint NOT NULL DEFAULT 0,
                updated_at  timestamptz NOT NULL DEFAULT now()
            )""")
        cur.execute("""
            CREATE TABLE held (
                id       bigserial PRIMARY KEY,
                scene_id text NOT NULL,
                worker   text NOT NULL,
                acquired timestamptz NOT NULL,
                released timestamptz NOT NULL
            )""")
        cur.execute("""
            CREATE TABLE write_log (
                id          bigserial PRIMARY KEY,
                scene_id    text NOT NULL,
                worker      text NOT NULL,
                token       bigint,
                still_owner boolean NOT NULL,
                accepted    boolean NOT NULL,
                at          timestamptz NOT NULL DEFAULT clock_timestamp()
            )""")
    conn.close()
    redis.from_url(RURL, decode_responses=True).flushdb()


def bump(r, field, n=1):
    r.hincrby(CNT, field, n)


def render_tiles(scene_id, worker, seconds):
    """CPU work standing in for tiling a scene; ~`seconds` of hashing."""
    h = hashlib.sha256(f"{scene_id}:{worker}".encode())
    buf = bytes(65536)
    for _ in range(int(seconds * ROUNDS_PER_SECOND)):
        h.update(hashlib.sha256(buf).digest())
    return h.hexdigest()[:16]


def write_result(conn, mode, scene_id, checksum, worker_id, token):
    with conn.cursor() as cur:
        if mode == "fenced":
            cur.execute("""
                INSERT INTO scene_product (scene_id, checksum, written_by, fence_token)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (scene_id) DO UPDATE
                SET checksum = EXCLUDED.checksum,
                    written_by = EXCLUDED.written_by,
                    fence_token = EXCLUDED.fence_token,
                    updated_at = now()
                WHERE scene_product.fence_token < EXCLUDED.fence_token
                """, (scene_id, checksum, worker_id, token))
        else:
            cur.execute("""
                INSERT INTO scene_product (scene_id, checksum, written_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (scene_id) DO UPDATE
                SET checksum = EXCLUDED.checksum,
                    written_by = EXCLUDED.written_by,
                    updated_at = now()
                """, (scene_id, checksum, worker_id))
        return cur.rowcount == 1


def heartbeat(r, key, me, stop):
    """Keeps the lock alive while this process is running."""
    script = r.register_script(EXTEND)
    while not stop.wait(LOCK_TTL_MS / 3000):
        script(keys=[key], args=[me, LOCK_TTL_MS])


def worker_loop(mode, worker_id, deadline):
    rng = random.Random(worker_id)
    r = redis.from_url(RURL, decode_responses=True)
    unlock_reporting = r.register_script(UNLOCK_REPORTING)
    unlock_safe = r.register_script(UNLOCK_SAFE)
    conn = db()

    while time.time() < deadline:
        scene_id = r.srandmember("pending")
        if scene_id is None:
            time.sleep(0.02)
            continue
        key = f"lock:scene:{scene_id}"
        me = str(uuid.uuid4())
        if not r.set(key, me, nx=True, px=LOCK_TTL_MS):
            bump(r, "contended")
            continue

        acquired = time.time()
        token = r.incr(f"fence:scene:{scene_id}") if mode == "fenced" else None
        bump(r, "processed")

        stop = threading.Event()
        hb = None
        if mode in ("watchdog", "fenced"):
            hb = threading.Thread(target=heartbeat, args=(r, key, me, stop),
                                  daemon=True)
            hb.start()

        checksum = render_tiles(scene_id, worker_id,
                                rng.uniform(*WORK_SECONDS))
        if rng.random() < STALL_PROBABILITY:
            bump(r, "stalls")
            r.rpush("stall_ms", int(rng.uniform(*STALL_SECONDS) * 1000))
            os.kill(os.getpid(), signal.SIGSTOP)

        if hb is not None:
            stop.set()
            hb.join(timeout=1)

        still_owner = r.get(key) == me
        if not still_owner:
            bump(r, "wrote_without_lock")
        accepted = write_result(conn, mode, scene_id, checksum, worker_id, token)
        if not accepted:
            bump(r, "rejected")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO write_log (scene_id, worker, token, still_owner,"
                " accepted) VALUES (%s,%s,%s,%s,%s)",
                (scene_id, worker_id, token, still_owner, accepted))
        r.srem("pending", scene_id)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO held (scene_id, worker, acquired, released)"
                " VALUES (%s,%s,to_timestamp(%s),to_timestamp(%s))",
                (scene_id, worker_id, acquired, time.time()))

        if mode == "naive":
            prev = unlock_reporting(keys=[key])
            if prev is None:
                bump(r, "unlock_key_already_gone")
            elif prev != me:
                bump(r, "unlocked_someone_else")
        else:
            unlock_safe(keys=[key], args=[me])
    conn.close()


def reviver(pids, deadline):
    """SIGCONT anything that froze itself, after its chosen stall."""
    r = redis.from_url(RURL, decode_responses=True)
    pending = {}
    while time.time() < deadline + STALL_SECONDS[1] + 3:
        now = time.time()
        for pid in pids:
            try:
                with open(f"/proc/{pid}/stat") as fh:
                    state = fh.read().rsplit(") ", 1)[1][0]
            except (OSError, IndexError):
                continue
            if state == "T" and pid not in pending:
                ms = r.lpop("stall_ms")
                pending[pid] = now + (int(ms) / 1000 if ms else STALL_SECONDS[0])
            elif state != "T":
                pending.pop(pid, None)
        for pid, when in list(pending.items()):
            if now >= when:
                try:
                    os.kill(pid, signal.SIGCONT)
                except ProcessLookupError:
                    pass
                pending.pop(pid, None)
        time.sleep(0.02)


def producer(deadline):
    """Scenes arrive from the satellite downlink at a steady rate."""
    r = redis.from_url(RURL, decode_responses=True)
    for scene_id in SCENES:
        if time.time() >= deadline:
            return
        r.sadd("pending", scene_id)
        time.sleep(ARRIVAL_SECONDS)


def run(mode, n_workers=6, seconds=45):
    setup()
    r = redis.from_url(RURL, decode_responses=True)
    deadline = time.time() + seconds

    started = time.perf_counter()
    procs = [mp.Process(target=worker_loop, args=(mode, f"w{i}", deadline))
             for i in range(n_workers)]
    for p in procs:
        p.start()
    aux = [mp.Process(target=reviver, args=([p.pid for p in procs], deadline)),
           mp.Process(target=producer, args=(deadline,))]
    for p in aux:
        p.start()
    for p in procs + aux:
        p.join()
    elapsed = time.perf_counter() - started

    c = {k: int(v) for k, v in r.hgetall(CNT).items()}
    conn = db()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM write_log")
        writes = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM write_log WHERE NOT still_owner")
        no_lock = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM write_log"
                    " WHERE NOT still_owner AND accepted")
        bad_ok = cur.fetchone()[0]
        cur.execute("""
            SELECT count(*) FROM scene_product p
            JOIN LATERAL (SELECT worker FROM held h
                          WHERE h.scene_id = p.scene_id
                          ORDER BY h.acquired DESC LIMIT 1) last_owner ON true
            WHERE p.written_by <> last_owner.worker
            """)
        corrupt = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM scene_product")
        rows = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM (SELECT scene_id FROM write_log"
                    " GROUP BY scene_id HAVING count(DISTINCT worker) > 1) t")
        multi = cur.fetchone()[0]
        cur.execute("""
            SELECT count(*) FROM held a JOIN held b
              ON a.scene_id = b.scene_id AND a.id < b.id
             AND a.acquired < b.released AND b.acquired < a.released
            """)
        overlaps = cur.fetchone()[0]
        cur.execute("""
            SELECT count(DISTINCT a.scene_id) FROM held a JOIN held b
              ON a.scene_id = b.scene_id AND a.id < b.id
             AND a.acquired < b.released AND b.acquired < a.released
            """)
        overlap_scenes = cur.fetchone()[0]
        cur.execute("""
            SELECT round(max(extract(epoch from
                     least(a.released, b.released) - greatest(a.acquired, b.acquired))
                   )::numeric, 2)
            FROM held a JOIN held b
              ON a.scene_id = b.scene_id AND a.id < b.id
             AND a.acquired < b.released AND b.acquired < a.released
            """)
        worst_overlap = cur.fetchone()[0]
    conn.close()

    print(f"\n=== mode={mode} workers={n_workers} ttl={LOCK_TTL_MS}ms "
          f"stall={STALL_SECONDS}s window={seconds}s ===")
    for label, val in [
            ("scenes", len(SCENES)),
            ("rows in scene_product", rows),
            ("work executions", c.get("processed", 0)),
            ("stop-the-world stalls", c.get("stalls", 0)),
            ("scenes touched by >1 worker", multi),
            ("overlapping ownership pairs", overlaps),
            ("scenes with two live owners", overlap_scenes),
            ("longest double ownership", f"{worst_overlap} s"),
            ("writes attempted", writes),
            ("writes made without the lock", no_lock),
            ("  ... of those, accepted", bad_ok),
            ("writes rejected by the db", c.get("rejected", 0)),
            ("unlocked someone else's lock", c.get("unlocked_someone_else", 0)),
            ("unlock found the key gone", c.get("unlock_key_already_gone", 0)),
            ("survivor is not the last owner", corrupt),
            ("wall clock", f"{elapsed:.1f}s")]:
        print(f"  {label:<34} {val}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "naive")
