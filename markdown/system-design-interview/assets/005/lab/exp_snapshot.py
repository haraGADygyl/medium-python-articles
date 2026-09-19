"""Capture the lock queue exactly as psql shows it during the stall."""
import subprocess
import threading
import time

import psycopg

from lab import DSN, Traffic, hold_reader, run_alter

SNAPSHOT = """
SELECT a.pid,
       left(a.query, 46) AS query,
       l.mode,
       l.granted,
       to_char(now() - a.query_start, 'SS.MS') AS waited_s
FROM pg_locks l
JOIN pg_stat_activity a USING (pid)
WHERE l.relation = 'meter_reading'::regclass
ORDER BY l.granted DESC, a.query_start;
"""


def main() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("ALTER TABLE meter_reading DROP COLUMN IF EXISTS "
                     "firmware_tag")
    traffic = Traffic()
    traffic.start()
    time.sleep(2.0)
    ready = threading.Event()
    threading.Thread(target=hold_reader, args=(12.0, ready),
                     daemon=True).start()
    ready.wait(5.0)
    time.sleep(0.5)
    threading.Thread(
        target=run_alter,
        args=("ALTER TABLE meter_reading ADD COLUMN firmware_tag text",
              None, 1), daemon=True).start()
    time.sleep(2.0)
    out = subprocess.run(
        ["docker", "exec", "-i", "ddl-lab", "psql", "-U", "postgres",
         "-c", SNAPSHOT], capture_output=True, text=True)
    print(out.stdout)
    with open("output-locks-snapshot.txt", "w") as fh:
        fh.write(out.stdout)
    traffic.stop.set()
    time.sleep(11)


if __name__ == "__main__":
    main()
