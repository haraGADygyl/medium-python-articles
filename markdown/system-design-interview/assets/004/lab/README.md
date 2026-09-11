# Lab for 004 — Downstream Recovers and Falls Over Again

The code behind every number in the article. Measured on a Ryzen 5 3600,
Python 3.12.3, aiohttp 3.9.1. No Docker — the downstream is `service.py`.

| File | What it is |
|---|---|
| `service.py` | The downstream: 40 slots, drops to `--degraded-slots` between `--down-at` and `--up-at` |
| `client.py` | 2000 closed-loop callers, retry policy `naive` / `jitter` / `budget` / `breaker` |
| `run.py` | Starts the service, runs one policy, prints client + server summary, writes `stats-<tag>.json` |
| `sweep.py` | Every policy in both scenarios (0.8s blip, 10s outage), writes `results.json` |
| `published.py` | The article's code blocks as printed |
| `output-sweep.txt` | The sweep the article's numbers come from |
| `out-*.txt`, `stats-*.json` | Earlier single-policy runs from `run.py` |

## Run

```bash
python3.12 -m venv .venv
.venv/bin/pip install aiohttp==3.9.1

.venv/bin/python sweep.py                  # ~10 minutes, all cases
.venv/bin/python run.py breaker 8091 8     # one policy: <policy> <port> <degraded slots>
.venv/bin/python run.py breaker 8091 8 --probe all --cool-steps 0
```

`run.py` reads `DOWN_AT`, `UP_AT` and `DURATION` from the environment
(defaults 6, 16, 60). `run.py` and `sweep.py` overwrite the `stats-*.json` and
`results.json` files here.
