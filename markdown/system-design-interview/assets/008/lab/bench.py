"""Throughput and latency of both handlers, no kills, no slow tail.

8 threads for 20 s per run; `hot` sends every checkout to one SKU, `spread`
across 500. Three rounds with the configurations interleaved, median printed.
"""
import os
import random
import statistics
import subprocess
import sys
import threading
import time
import uuid

from checkout import Declined, checkout_in_transaction, checkout_saga
from common import shop

THREADS, SECONDS, ROUNDS = 8, 20, 3
HERE = os.path.dirname(os.path.abspath(__file__))
HANDLERS = {"transaction": checkout_in_transaction, "saga": checkout_saga}


def run(mode: str, skus: str) -> tuple[float, float, float]:
    handler, latencies, lock = HANDLERS[mode], [], threading.Lock()
    deadline = time.monotonic() + SECONDS

    def loop() -> None:
        conn, mine = shop(), []
        while time.monotonic() < deadline:
            sku = "HOT-1" if skus == "hot" else f"SKU-{random.randint(1, 500)}"
            started = time.perf_counter()
            try:
                handler(conn, f"co_{uuid.uuid4().hex[:16]}", sku, 4200, "card_ok")
            except Declined:
                continue
            mine.append((time.perf_counter() - started) * 1000)
        with lock:
            latencies.extend(mine)

    threads = [threading.Thread(target=loop) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    q = statistics.quantiles(latencies, n=100)
    return len(latencies) / SECONDS, q[49], q[98]


subprocess.run(["docker", "exec", "-i", "saga-pg", "psql", "-qU", "postgres"],
               stdin=open(os.path.join(HERE, "schema.sql")), check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
provider = subprocess.Popen([sys.executable, "provider.py"], cwd=HERE,
                            env={**os.environ, "TAIL_P": "0"})
time.sleep(1)
configs = [(m, s) for s in ("spread", "hot") for m in ("transaction", "saga")]
results = {c: [] for c in configs}
for _ in range(ROUNDS):
    for c in configs:
        results[c].append(run(*c))
provider.terminate()

print(f"{THREADS} threads, {SECONDS} s per run, median of {ROUNDS} interleaved rounds")
print(f"{'handler':<12}{'skus':<8}{'checkouts/s':>12}{'p50 ms':>9}{'p99 ms':>9}")
for (mode, skus), runs in results.items():
    rate, p50, p99 = (statistics.median(r[i] for r in runs) for i in range(3))
    print(f"{mode:<12}{skus:<8}{rate:>12.1f}{p50:>9.1f}{p99:>9.1f}")
