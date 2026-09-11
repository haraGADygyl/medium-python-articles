# Lab for 003 — Two Workers Hold the Same Lock

The code behind every number in the article and in `../comments.md`.
Measured on a Ryzen 5 3600, Python 3.12.3.

| File | What it is |
|---|---|
| `lab.py` | Main experiment: 6 workers, 80 scenes, 30% `SIGSTOP` stalls. Modes `naive`, `watchdog`, `fenced` |
| `bench.py` | Watchdog-vs-`SIGSTOP` four-cell test and the fencing cost benchmark |
| `verify.py` | Runs the article's code blocks exactly as printed |
| `lab_deadline.py` | Reader follow-up (2026-09-11): TTL 2.5s + skip the write if >2s elapsed |
| `output-deadline-guard.txt` | Output of the `lab_deadline.py` run quoted in `../comments.md` |

## Run

```bash
docker run -d --name lab003-redis -p 6399:6379 redis:7.4.11
docker run -d --name lab003-pg -p 5442:5432 \
  -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=scenes postgres:17.6
# after the first time: docker start lab003-redis lab003-pg

python3.12 -m venv .venv
.venv/bin/pip install psycopg2-binary==2.9.12 redis==8.1.0

.venv/bin/python lab.py naive            # or watchdog / fenced
.venv/bin/python bench.py
.venv/bin/python lab_deadline.py guard-stall-in-work
.venv/bin/python lab_deadline.py guard-stall-after-check
.venv/bin/python lab_deadline.py guard-fenced-after-check
```

Each `lab*.py` run takes about 50 seconds and wipes the tables and Redis db 0 first.
Stalls are random, so re-runs land near the published numbers, not on them.
