"""Run checkout workers for DURATION seconds and SIGKILL one every KILL_MS.

python3 storm.py transaction
python3 storm.py saga lookup
python3 storm.py saga redrive
"""
import os
import random
import signal
import subprocess
import sys
import tempfile
import time

from common import shop
from reconcile import reconcile

MODE = sys.argv[1]
SWEEP = sys.argv[2] if len(sys.argv) > 2 else None
WORKERS = int(os.environ.get("WORKERS", "8"))
DURATION = float(os.environ.get("DURATION", "60"))
KILL_MS = float(os.environ.get("KILL_MS", "500"))
SEED = int(os.environ.get("SEED", "8"))
HERE = os.path.dirname(os.path.abspath(__file__))

random.seed(SEED)
subprocess.run(["docker", "exec", "-i", "saga-pg", "psql", "-qU", "postgres"],
               stdin=open(os.path.join(HERE, "schema.sql")), check=True,
               stdout=subprocess.DEVNULL)
stop = os.path.join(tempfile.mkdtemp(), "stop")
provider = subprocess.Popen([sys.executable, "provider.py"], cwd=HERE)
time.sleep(1)


stop_sweeper = stop + "-sweeper"


def spawn(*args: str, until: str = stop) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, *args, until], cwd=HERE)


workers = [spawn("worker.py", MODE) for _ in range(WORKERS)]
sweeper = spawn("sweeper.py", SWEEP, until=stop_sweeper) if SWEEP else None
kills = 0
started = time.monotonic()
while time.monotonic() - started < DURATION:
    time.sleep(KILL_MS / 1000)
    victim = random.randrange(WORKERS)
    workers[victim].send_signal(signal.SIGKILL)
    workers[victim].wait()
    workers[victim] = spawn("worker.py", MODE)
    kills += 1

open(stop, "w").close()
for w in workers:
    try:
        w.wait(timeout=20)
    except subprocess.TimeoutExpired:
        w.kill()
# let every in-flight provider request land, then let the sweeper drain
time.sleep(float(os.environ.get("TAIL_MAX", "8")) + 2)
if sweeper:
    with shop() as conn:
        while conn.execute("SELECT count(*) FROM checkout "
                           "WHERE state = 'pending'").fetchone()[0]:
            time.sleep(0.5)
    open(stop_sweeper, "w").close()
    sweeper.wait()
provider.terminate()

env = {k: os.environ.get(k) for k in ("TAIL_P", "STALE_S") if os.environ.get(k)}
print(f"mode={MODE}{'/' + SWEEP if SWEEP else ''} workers={WORKERS} "
      f"duration={DURATION:.0f}s kills={kills} {env}")
for k, v in reconcile().items():
    print(f"{k:<30}{v}")
