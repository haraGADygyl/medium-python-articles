import hashlib
import threading
import time
import uuid

import psycopg2
import redis

PG = "host=127.0.0.1 port=5442 dbname=scenes user=postgres password=demo"
LOCK_TTL_MS = 2000
ROUNDS_PER_SECOND = 25000

pool = redis.from_url("redis://127.0.0.1:6399/0", decode_responses=True)


def connect_db():
    """One autocommit connection per worker process."""
    conn = psycopg2.connect(PG)
    conn.autocommit = True
    return conn


def render_tiles(scene_id: str, worker_id: str, seconds: float) -> str:
    """Stands in for tiling a scene: roughly `seconds` of hashing."""
    digest = hashlib.sha256(f"{scene_id}:{worker_id}".encode())
    block = bytes(65536)
    for _ in range(int(seconds * ROUNDS_PER_SECOND)):
        digest.update(hashlib.sha256(block).digest())
    return digest.hexdigest()[:16]
def process_naive(scene_id: str, worker_id: str, work_seconds: float) -> bool:
    """Take the lock, tile the scene, write the result, release."""
    key = f"lock:scene:{scene_id}"
    me = str(uuid.uuid4())
    if not pool.set(key, me, nx=True, px=LOCK_TTL_MS):
        return False
    conn = connect_db()
    try:
        checksum = render_tiles(scene_id, worker_id, work_seconds)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scene_product (scene_id, checksum, written_by)
                VALUES (%s, %s, %s)
                ON CONFLICT (scene_id) DO UPDATE
                SET checksum = EXCLUDED.checksum,
                    written_by = EXCLUDED.written_by,
                    updated_at = now()
                """, (scene_id, checksum, worker_id))
        return True
    finally:
        conn.close()
        pool.delete(key)
UNLOCK_IF_MINE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

EXTEND_IF_MINE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""

unlock_if_mine = pool.register_script(UNLOCK_IF_MINE)
extend_if_mine = pool.register_script(EXTEND_IF_MINE)


def heartbeat(key: str, me: str, stop: threading.Event) -> None:
    """Renews the lease every third of the TTL until told to stop."""
    while not stop.wait(LOCK_TTL_MS / 3000):
        extend_if_mine(keys=[key], args=[me, LOCK_TTL_MS])
def process_fenced(scene_id: str, worker_id: str, work_seconds: float) -> bool:
    """Same lock, plus a token the write has to justify itself with."""
    key = f"lock:scene:{scene_id}"
    me = str(uuid.uuid4())
    if not pool.set(key, me, nx=True, px=LOCK_TTL_MS):
        return False
    token = pool.incr(f"fence:scene:{scene_id}")
    stop = threading.Event()
    beat = threading.Thread(target=heartbeat, args=(key, me, stop), daemon=True)
    beat.start()
    conn = connect_db()
    try:
        checksum = render_tiles(scene_id, worker_id, work_seconds)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scene_product (scene_id, checksum, written_by,
                                           fence_token)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (scene_id) DO UPDATE
                SET checksum = EXCLUDED.checksum,
                    written_by = EXCLUDED.written_by,
                    fence_token = EXCLUDED.fence_token,
                    updated_at = now()
                WHERE scene_product.fence_token < EXCLUDED.fence_token
                """, (scene_id, checksum, worker_id, token))
            return cur.rowcount == 1        # False means: you are stale
    finally:
        stop.set()
        beat.join(timeout=1)
        conn.close()
        unlock_if_mine(keys=[key], args=[me])


import psycopg2 as _pg
_c = _pg.connect(PG); _c.autocommit = True
with _c.cursor() as _cur:
    _cur.execute("DROP TABLE IF EXISTS scene_product")
    _cur.execute("""CREATE TABLE scene_product (
    scene_id    text PRIMARY KEY,
    checksum    text NOT NULL,
    written_by  text NOT NULL,
    fence_token bigint NOT NULL DEFAULT 0,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
""")
_c.close()
print("naive:", process_naive("VERIFY-1", "w0", 0.2))
print("fenced:", process_fenced("VERIFY-1", "w0", 0.2))
print("fenced again:", process_fenced("VERIFY-1", "w1", 0.2))
_c = _pg.connect(PG)
with _c.cursor() as _cur:
    _cur.execute("SELECT scene_id, written_by, fence_token FROM scene_product")
    print(_cur.fetchall())
_c.close()

