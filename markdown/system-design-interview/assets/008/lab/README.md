# Lab — 008, a payment succeeded but the order was never created

PostgreSQL 17.6 (`postgres:17`) in Docker, Python 3.12.3, `psycopg[binary]==3.2.3`,
everything else from the standard library. Ryzen 5 3600, NVMe.

```bash
docker run -d --name saga-pg -e POSTGRES_PASSWORD=lab -p 55438:5432 \
  postgres:17 -c max_connections=200 -c shared_buffers=512MB
pip install "psycopg[binary]==3.2.3"
./run_storms.sh     # ~16 min, writes output-storm-*.txt
python3 bench.py > output-bench.txt    # ~5 min
python3 summary.py > output-summary.txt
```

Two databases in one container, and no code path that uses both in one
transaction. `shop` belongs to the checkout service: `stock` (500 SKUs plus
`HOT-1`), `checkout` (the saga state) and `orders`. `provider` belongs to the
payment provider, which is its own process (`provider.py`, stdlib HTTP server on
127.0.0.1:8099) with an idempotent `POST /charges` (unique key, `ON CONFLICT DO
NOTHING`) and `GET /charges?key=`. Each request spends 40–60 ms in flight before
the provider records anything and 40–60 ms on the way back. With `TAIL_P=0.02`,
2% of requests are instead held 1–8 s before they arrive.

| File | What it is |
| --- | --- |
| `checkout.py` | `checkout_in_transaction` (the obvious answer) and the three saga steps |
| `worker.py` | one checkout worker process, loops until a stop file appears; 5% of cards decline |
| `sweeper.py` | resolves checkouts pending > `STALE_S`: `lookup` asks the provider, `redrive` re-sends the same charge |
| `storm.py` | 8 workers for 60 s, SIGKILL a random one every 500 ms and respawn it, drain, reconcile |
| `reconcile.py` | provider charges vs shop orders: charged with no order, order with no charge, stock invariant |
| `bench.py` | 8 threads, 20 s per run, 3 interleaved rounds, no kills, no tail |
| `orphans.py` | for each charge with no order, how long it spent in flight before the provider recorded it |

| Experiment | Command | Output |
| --- | --- | --- |
| One transaction around everything, kill storm | `TAIL_P=0 python3 storm.py transaction` (x3) | `output-storm-transaction.txt` |
| Saga, lookup sweeper, no slow requests | `TAIL_P=0 STALE_S=2 python3 storm.py saga lookup` | `output-storm-lookup-notail.txt` |
| Saga, lookup sweeper, 2% slow requests | `TAIL_P=0.02 STALE_S=2 python3 storm.py saga lookup` (x3) | `output-storm-lookup.txt` |
| Same, sweeper waits 5 s | `TAIL_P=0.02 STALE_S=5 python3 storm.py saga lookup` | `output-storm-lookup-5s.txt` |
| Saga, re-drive sweeper, 2% slow requests | `TAIL_P=0.02 STALE_S=2 python3 storm.py saga redrive` (x3) | `output-storm-redrive.txt` |
| Throughput and latency, spread and hot SKU | `python3 bench.py` | `output-bench.txt` |
| In-flight time of every orphan, after a 30 s lookup storm | `python3 orphans.py` | `output-orphans.txt` |
| One line per storm run | `python3 summary.py` | `output-summary.txt` |

`SEED` only seeds the harness (which worker is killed); workers and the provider
draw their own randomness, so repeated runs differ.

After the workers stop, `storm.py` waits `TAIL_MAX + 2` s for every in-flight
provider request to land, then lets the sweeper run until nothing is pending, so
a late charge is always counted.

Teardown: `docker rm -f saga-pg`.
