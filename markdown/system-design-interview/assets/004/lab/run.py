"""Start the service, run one policy against it, print client + server view."""
import json
import subprocess
import sys
import time
import urllib.request

import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOWN_AT = float(os.environ.get("DOWN_AT", 6.0))
UP_AT = float(os.environ.get("UP_AT", 16.0))
DURATION = float(os.environ.get("DURATION", 60.0))


def run(policy, port, degraded=8, duration=DURATION, extra=()):
    svc = subprocess.Popen(
        [sys.executable, f"{HERE}/service.py", "--port", str(port),
         "--degraded-slots", str(degraded),
         "--down-at", str(DOWN_AT), "--up-at", str(UP_AT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    svc.stdout.readline()
    time.sleep(0.7)
    out = subprocess.run(
        [sys.executable, f"{HERE}/client.py", policy, "--port", str(port),
         "--duration", str(duration), "--recovery-at", str(UP_AT),
         *extra],
        capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stdout, out.stderr)
        svc.kill()
        sys.exit(1)
    client = json.loads(out.stdout.strip().splitlines()[-1])
    stats = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:{port}/admin/stats", timeout=30).read())
    svc.terminate()
    svc.wait(timeout=10)
    return client, stats


def summarize(client, stats):
    rows, b = stats["rows"], stats["bucket"]
    rate = lambda rs: [r["arrived"] / b for r in rs]
    steady = [r for r in rows if 2.0 <= r["t"] < DOWN_AT]
    outage = [r for r in rows if DOWN_AT <= r["t"] < UP_AT]
    recov = [r for r in rows if UP_AT <= r["t"] < UP_AT + 6.0]
    tl = client["timeline"]
    recovered = None
    for row in tl:
        if row["sec"] >= UP_AT and row["fail"] == 0 and row["ok"] > 0:
            if all(r["fail"] == 0 for r in tl
                   if row["sec"] <= r["sec"] < row["sec"] + 3):
                recovered = row["sec"]
                break
    out = {k: v for k, v in client.items() if k != "timeline"}
    out["steady_rps"] = round(sum(rate(steady)) / max(1, len(steady)))
    out["outage_rps"] = round(sum(rate(outage)) / max(1, len(outage)))
    out["outage_peak_rps"] = round(max(rate(outage) or [0]))
    out["recovery_rps"] = round(sum(rate(recov)) / max(1, len(recov)))
    out["recovery_peak_rps"] = round(max(rate(recov) or [0]))
    out["recovery_max_queue"] = max((r["max_waiting"] for r in recov),
                                    default=0)
    served = sum(r["ok"] for r in rows)
    out["server_arrived"] = sum(r["arrived"] for r in rows)
    out["server_served"] = served
    out["dead_work"] = served - client["succeeded"]
    out["dead_work_pct"] = round(100 * (served - client["succeeded"])
                                 / max(1, served), 1)
    out["queue_max"] = max(r["max_waiting"] for r in rows)
    out["queue_max_at"] = max(rows, key=lambda r: r["max_waiting"])["t"]
    out["recovered_at_s"] = recovered
    return out


if __name__ == "__main__":
    policy = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8091
    degraded = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    c, s = run(policy, port, degraded, extra=sys.argv[4:])
    summary = summarize(c, s)
    print(json.dumps(summary, indent=2))
    print("\nsec  attempts   ok  fail skip")
    for r in c["timeline"]:
        print(f"{r['sec']:3d} {r['attempts']:9d} {r['ok']:4d} "
              f"{r['fail']:5d} {r['skipped']:4d}")
    tag = policy + ("-" + "-".join(a.lstrip("-") for a in sys.argv[4:])
                    if len(sys.argv) > 4 else "")
    with open(f"{HERE}/stats-{tag}.json", "w") as fh:
        json.dump({"client": c, "server": s, "summary": summary}, fh)
