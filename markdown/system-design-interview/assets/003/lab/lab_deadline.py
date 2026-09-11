"""Reader's proposal: TTL 2.5s, skip the write if >2s elapsed since SET.

Modes:
  guard-stall-in-work     stall lands during tiling, before the guard check
  guard-stall-after-check stall lands after the guard passes, before the write
  guard-fenced-after-check  same as above, plus fencing tokens on the write
"""
import multiprocessing as mp
import os
import random
import signal
import sys
import time
import uuid

import redis

import lab
from lab import CNT, RURL, SCENES, bump, db, render_tiles, write_result

LOCK_TTL_MS = 2500
GUARD_SECONDS = 2.0


def worker_loop(mode, worker_id, deadline):
    rng = random.Random(worker_id)
    r = redis.from_url(RURL, decode_responses=True)
    unlock_safe = r.register_script(lab.UNLOCK_SAFE)
    conn = db()
    write_mode = "fenced" if "fenced" in mode else "plain"
    stall_after_check = mode != "guard-stall-in-work"

    def maybe_stall():
        if rng.random() < lab.STALL_PROBABILITY:
            bump(r, "stalls")
            r.rpush("stall_ms", int(rng.uniform(*lab.STALL_SECONDS) * 1000))
            os.kill(os.getpid(), signal.SIGSTOP)

    while time.time() < deadline:
        scene_id = r.srandmember("pending")
        if scene_id is None:
            time.sleep(0.02)
            continue
        key = f"lock:scene:{scene_id}"
        me = str(uuid.uuid4())
        started = time.monotonic()                  # before SET: most generous
        if not r.set(key, me, nx=True, px=LOCK_TTL_MS):
            bump(r, "contended")
            continue
        acquired = time.time()
        token = r.incr(f"fence:scene:{scene_id}")   # issued in every mode
        bump(r, "processed")

        checksum = render_tiles(scene_id, worker_id, rng.uniform(*lab.WORK_SECONDS))
        if not stall_after_check:
            maybe_stall()

        elapsed = time.monotonic() - started
        if elapsed > GUARD_SECONDS:                 # the reader's check
            bump(r, "guard_skipped")
            if int(r.get(f"fence:scene:{scene_id}")) == token:
                bump(r, "guard_skipped_while_newest")
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO held (scene_id, worker, acquired, released)"
                    " VALUES (%s,%s,to_timestamp(%s),to_timestamp(%s))",
                    (scene_id, worker_id, acquired, time.time()))
            unlock_safe(keys=[key], args=[me])
            continue
        r.rpush("guard_passed_at_ms", int(elapsed * 1000))

        if stall_after_check:
            maybe_stall()

        still_owner = r.get(key) == me
        if not still_owner:
            bump(r, "wrote_without_lock")
        accepted = write_result(conn, write_mode, scene_id, checksum,
                                worker_id, token)
        if not accepted:
            bump(r, "rejected")
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO write_log (scene_id, worker, token, still_owner,"
                " accepted) VALUES (%s,%s,%s,%s,%s)",
                (scene_id, worker_id, token, still_owner, accepted))
            cur.execute(
                "INSERT INTO held (scene_id, worker, acquired, released)"
                " VALUES (%s,%s,to_timestamp(%s),to_timestamp(%s))",
                (scene_id, worker_id, acquired, time.time()))
        r.srem("pending", scene_id)
        unlock_safe(keys=[key], args=[me])
    conn.close()


def one(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def run(mode, n_workers=6, seconds=45):
    lab.setup()
    r = redis.from_url(RURL, decode_responses=True)
    deadline = time.time() + seconds
    t0 = time.perf_counter()
    procs = [mp.Process(target=worker_loop, args=(mode, f"w{i}", deadline))
             for i in range(n_workers)]
    for p in procs:
        p.start()
    aux = [mp.Process(target=lab.reviver, args=([p.pid for p in procs], deadline)),
           mp.Process(target=lab.producer, args=(deadline,))]
    for p in aux:
        p.start()
    for p in procs + aux:
        p.join()
    wall = time.perf_counter() - t0

    c = {k: int(v) for k, v in r.hgetall(CNT).items()}
    passed = sorted(int(x) for x in r.lrange("guard_passed_at_ms", 0, -1))
    conn = db()
    with conn.cursor() as cur:
        overlap = """FROM held a JOIN held b
              ON a.scene_id = b.scene_id AND a.id < b.id
             AND a.acquired < b.released AND b.acquired < a.released"""
        overlap_scenes = one(cur, f"SELECT count(DISTINCT a.scene_id) {overlap}")
        worst = one(cur, f"""SELECT round(max(extract(epoch from
                 least(a.released, b.released) - greatest(a.acquired, b.acquired))
                 )::numeric, 2) {overlap}""")
        writes = one(cur, "SELECT count(*) FROM write_log")
        no_lock = one(cur, "SELECT count(*) FROM write_log WHERE NOT still_owner")
        no_lock_ok = one(cur, "SELECT count(*) FROM write_log"
                              " WHERE NOT still_owner AND accepted")
        # a scene is corrupt if the result it ends with came from an older
        # lock holder than some other result that was accepted for it
        corrupt = one(cur, """
            SELECT count(*) FROM (
              SELECT scene_id FROM write_log WHERE accepted GROUP BY scene_id
              HAVING (array_agg(token ORDER BY at DESC))[1] < max(token)) t""")
        rows = one(cur, "SELECT count(*) FROM scene_product")
    conn.close()

    print(f"\n=== {mode}: {n_workers} workers, ttl={LOCK_TTL_MS}ms, "
          f"guard={GUARD_SECONDS:.1f}s, stall={lab.STALL_SECONDS}s ===")
    for label, val in [
            ("rows in scene_product", f"{rows} / {len(SCENES)}"),
            ("work executions", c.get("processed", 0)),
            ("stop-the-world stalls", c.get("stalls", 0)),
            ("guard: write skipped", c.get("guard_skipped", 0)),
            ("  ... skipped while still newest", c.get("guard_skipped_while_newest", 0)),
            ("guard: passed at (max)", f"{passed[-1] if passed else '-'} ms"),
            ("scenes with two live owners", overlap_scenes),
            ("longest double ownership", f"{worst} s"),
            ("writes attempted", writes),
            ("writes made without the lock", no_lock),
            ("  ... of those, accepted", no_lock_ok),
            ("writes rejected by the db", c.get("rejected", 0)),
            ("newer result overwritten", corrupt),
            ("wall clock", f"{wall:.1f}s")]:
        print(f"  {label:<34} {val}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "guard-stall-after-check")
