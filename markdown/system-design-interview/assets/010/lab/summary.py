"""The sweep table the article quotes, from output-trending-*.txt and
output-memcheck.txt (MEMORY USAGE over-reports CMS keys, so the KB column
comes from used_memory)."""
import re

real_kb = {}

for line in open("output-memcheck.txt"):
    m = re.match(r"width ([\d,]+) x depth 7: .* used_memory per sketch ([\d,]+) B", line)

    if m:
        real_kb[int(m[1].replace(",", ""))] = int(m[2].replace(",", "")) / 1e3

rows = {}

for seed in (1, 2, 3):
    for line in open(f"output-trending-{seed}.txt"):
        parts = line.split()

        if len(parts) > 12 and parts[0].replace(",", "").isdigit() and "|" in parts:
            width = int(parts[0].replace(",", ""))
            bar = parts.index("|")
            rows.setdefault(width, []).append({
                "floor": int(parts[2].replace(",", "")),
                "pass": int(parts[bar + 1]), "new": int(parts[bar + 2]),
                "ever": int(parts[bar + 3]), "ghost": int(parts[bar + 4]),
                "shown": float(parts[bar + 6]), "true": float(parts[bar + 8]),
            })

print("rule: >= 500 uses, lift >= 5; 30 new tags; seeds 1 / 2 / 3")
print(f"{'width':>7} {'KB/sketch':>9}   {'noise floor':<22} {'new pass':<16} {'others pass':<17} new-tag lift shown")

for width, runs in sorted(rows.items()):
    f = " / ".join(f"{x['floor']:,}" for x in runs)
    n = " / ".join(str(x["new"]) for x in runs)
    o = " / ".join(str(x["ever"] + x["ghost"]) for x in runs)
    s = " / ".join(f"{x['shown']:.1f}" for x in runs)
    print(f"{width:>7,} {real_kb[width]:>9,.0f}   {f:<22} {n:<16} {o:<17} {s}")
