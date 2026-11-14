"""Shared connections and helpers for the read-your-writes lab."""
import statistics
import threading
import time

import psycopg

PRIMARY = "host=127.0.0.1 port=55441 user=postgres password=lab dbname=postgres"
REPLICA = "host=127.0.0.1 port=55442 user=postgres password=lab dbname=postgres"


def connect(dsn: str) -> psycopg.Connection:
    """Autocommit connection, as a web request would use it."""
    return psycopg.connect(dsn, autocommit=True)


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0

    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * len(ordered)) - 1))

    return ordered[k]


def med(values: list[float]) -> float:
    return statistics.median(values) if values else 0.0


class LagSampler(threading.Thread):
    """Every 100 ms: bytes the replica has not replayed, and seconds behind.

    Seconds behind comes from a heartbeat row: the primary stamps it with its
    clock, the replica reads it back and subtracts from its own clock (same
    machine, same clock). Resolution is the 100 ms interval.
    """

    def __init__(self, t0: float) -> None:
        super().__init__(daemon=True)
        self.t0 = t0
        self.samples: list[tuple[float, int, float]] = []
        self.stop = threading.Event()

    def run(self) -> None:
        prim, rep = connect(PRIMARY), connect(REPLICA)

        while not self.stop.is_set():
            prim.execute("UPDATE heartbeat SET ts = clock_timestamp()")
            head = prim.execute("SELECT pg_current_wal_lsn()").fetchone()[0]
            behind, secs = rep.execute(
                "SELECT pg_wal_lsn_diff(%s::pg_lsn, pg_last_wal_replay_lsn()),"
                " extract(epoch FROM clock_timestamp() - ts) FROM heartbeat",
                (str(head),)).fetchone()
            self.samples.append((time.monotonic() - self.t0, int(behind),
                                 float(secs or 0)))
            time.sleep(0.1)
