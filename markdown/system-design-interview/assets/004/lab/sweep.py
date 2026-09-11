"""Both scenarios, every policy, one results file."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CASES = [
    # tag, down_at, up_at, policy, extra args
    ("blip-naive",    6.0, 6.8,  "naive",   []),
    ("blip-jitter",   6.0, 6.8,  "jitter",  []),
    ("blip-budget",   6.0, 6.8,  "budget",  []),
    ("blip-breaker",  6.0, 6.8,  "breaker", []),
    ("out-naive",     6.0, 16.0, "naive",   []),
    ("out-jitter",    6.0, 16.0, "jitter",  []),
    ("out-budget",    6.0, 16.0, "budget",  []),
    ("out-breaker-exp", 6.0, 16.0, "breaker", []),
    ("out-breaker-all", 6.0, 16.0, "breaker",
     ["--probe", "all", "--cool-steps", "0"]),
    ("out-breaker-cap", 6.0, 16.0, "breaker",
     ["--probe", "single", "--cool-steps", "1"]),
]

results = {}
port = 8300
for tag, down, up, policy, extra in CASES:
    os.environ["DOWN_AT"] = str(down)
    os.environ["UP_AT"] = str(up)
    os.environ["DURATION"] = "60"
    for mod in [m for m in list(sys.modules) if m == "run"]:
        del sys.modules[mod]
    import run as R
    port += 1
    client, stats = R.run(policy, port, 8, 60.0, extra)
    results[tag] = {"summary": R.summarize(client, stats),
                    "timeline": client["timeline"],
                    "server_rows": stats["rows"]}
    s = results[tag]["summary"]
    print(f"{tag:18s} amp={s['amplification']:5.2f} "
          f"offered={s['outage_rps']:5d} peak={s['outage_peak_rps']:5d} "
          f"qmax={s['queue_max']:6d} dead={s['dead_work_pct']:5.1f}% "
          f"recovered={str(s['recovered_at_s']):>5s} "
          f"failed={s['failed']:6d} ok={s['succeeded']:6d}", flush=True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "results.json"), "w") as fh:
    json.dump(results, fh)
print("SWEEP DONE")
