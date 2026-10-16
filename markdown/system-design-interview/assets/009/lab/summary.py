"""Print the three tables the article quotes, from the raw output files."""
import re

runs = re.findall(r"== round (\d) (\S+)\n(?:.*\n)*?updates \d+  hot% ([\d.]+)  "
                  r"wal bytes/update (\d+)  wal MB \d+  heap MB \d+  "
                  r"indexes MB (\d+)  autovacuums (\d+)",
                  open("output-pg-sustained.txt").read())
start = dict(re.findall(r"== (\S+): rate.*\n(?:.*\n)*?heap MB .*indexes MB (\d+) ->",
                        open("output-pg.txt").read()))
print("config     round   HOT updates   WAL bytes/heartbeat   indexes MB   autovacuums")
for config in ("no_index", "index"):
    for rnd, cfg, hot, wal, idx, av in runs:
        if cfg == config:
            name = cfg.replace("_", " ")
            print(f"{name:<10} {rnd:>5} {hot + '%':>13} {wal:>21} "
                  f"{start[cfg]:>6} -> {idx:<3} {av:>11}")
print()

pg = open("output-pg.txt").read()
print("online count during 10,000 heartbeats/s, 20 runs each")
for cfg, block in re.findall(r"== (\S+): rate(.*?)(?===|\Z)", pg, re.S):
    avg = re.search(r"-- online count.*?\nlatency average = ([\d.]+) ms", block, re.S)[1]
    scan = re.search(r"->  (Parallel Seq Scan|Index Only Scan|Parallel Index Only Scan)"
                     r".*?rows=(\d+) loops=(\d+)", block)
    fetches = re.search(r"Heap Fetches: (\d+)", block)
    rows = int(scan[2]) * int(scan[3])
    detail = scan[1] + (f", Heap Fetches: {fetches[1]} of {rows} rows" if fetches else "")
    print(f"{cfg.replace('_', ' '):<10} {detail:<56} {float(avg):.1f} ms average")
print()

print("window   flaps per user-hour   shown online after leaving (p50 / max)")
for line in open("output-window.txt"):
    m = re.search(r"= +(\d+) s +flaps/user-hour +([\d.]+) +ghost p50 +([\d.]+) s.*max +([\d.]+) s", line)
    print(f"{m[1] + ' s':<8} {m[2]:>19} {m[3] + ' s / ' + m[4] + ' s':>24}")
