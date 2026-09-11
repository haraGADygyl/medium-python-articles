"""Two micro-experiments: does the watchdog help, and what does fencing cost."""
import os
import signal
import statistics
import sys
import threading
import time
import uuid

sys.path.insert(0, ".")
import redis  # noqa: E402
from lab import (EXTEND, LOCK_TTL_MS, RURL, db, heartbeat, setup)  # noqa: E402

r = redis.from_url(RURL, decode_responses=True)


def watchdog_experiment(stall, use_watchdog, work=5.0):
    key = "lock:probe"
    r.delete(key)
    me = str(uuid.uuid4())
    r.set(key, me, nx=True, px=LOCK_TTL_MS)
    stop = threading.Event()
    hb = None
    if use_watchdog:
        hb = threading.Thread(target=heartbeat, args=(r, key, me, stop),
                              daemon=True)
        hb.start()
    if stall:
        pid = os.fork()
        if pid == 0:
            time.sleep(work)
            os.kill(os.getppid(), signal.SIGCONT)
            os._exit(0)
        os.kill(os.getpid(), signal.SIGSTOP)
        os.waitpid(pid, 0)
    else:
        deadline = time.time() + work
        while time.time() < deadline:      # busy work, threads still scheduled
            pow(3, 100000, 7919)
    if hb:
        stop.set()
        hb.join(timeout=1)
    held = r.get(key) == me
    r.delete(key)
    return held


def cost(mode, n=3000):
    conn = db()
    scene = "COST-0001"
    with conn.cursor() as cur:
        cur.execute("DELETE FROM scene_product WHERE scene_id = %s", (scene,))
    samples = []
    for i in range(n):
        t0 = time.perf_counter()
        key = f"lock:{scene}"
        me = str(uuid.uuid4())
        r.set(key, me, nx=True, px=LOCK_TTL_MS)
        if mode == "fenced":
            token = r.incr(f"fence:{scene}")
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scene_product (scene_id, checksum, written_by,
                                               fence_token)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (scene_id) DO UPDATE
                    SET checksum = EXCLUDED.checksum,
                        written_by = EXCLUDED.written_by,
                        fence_token = EXCLUDED.fence_token,
                        updated_at = now()
                    WHERE scene_product.fence_token < EXCLUDED.fence_token
                    """, (scene, "deadbeefdeadbeef", "bench", token))
        else:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO scene_product (scene_id, checksum, written_by)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (scene_id) DO UPDATE
                    SET checksum = EXCLUDED.checksum,
                        written_by = EXCLUDED.written_by,
                        updated_at = now()
                    """, (scene, "deadbeefdeadbeef", "bench"))
        r.delete(key)
        samples.append((time.perf_counter() - t0) * 1000)
    conn.close()
    samples.sort()
    return (statistics.mean(samples), samples[len(samples) // 2],
            samples[int(len(samples) * 0.99)])


if __name__ == "__main__":
    setup()
    print("=== does the watchdog keep the lock alive? "
          f"(ttl={LOCK_TTL_MS}ms, work=5s) ===")
    for stall in (False, True):
        for wd in (False, True):
            held = watchdog_experiment(stall, wd)
            label = "SIGSTOP (stop-the-world)" if stall else "slow but running"
            print(f"  {label:<26} watchdog={str(wd):<5} "
                  f"lock still mine at the end: {held}")

    print("\n=== cost of fencing: lock + write, 3000 iterations ===")
    for mode in ("plain", "fenced", "plain", "fenced"):
        mean, p50, p99 = cost(mode)
        print(f"  {mode:<7} mean {mean:.3f} ms   p50 {p50:.3f} ms   "
              f"p99 {p99:.3f} ms")
