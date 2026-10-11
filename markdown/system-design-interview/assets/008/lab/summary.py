"""One line per storm run, from the output-storm-*.txt files."""
import glob
import re

# no order: charged with no order; failed: of those, checkout marked failed;
# slow: provider requests that arrived (were recorded) after more than 1 s
FIELDS = {"kills": r"kills=(\d+)", "charged": r"charges succeeded\s+(\d+)",
          "orders": r"orders\s+(\d+)", "no order": r"charged, no order\s+(\d+)",
          "failed": r"checkout failed\s+(\d+)",
          "slow": r"held > 1 s \(max ms\)\s+(\d+)"}
print(f"{'run':<28}" + "".join(f"{k:>9}" for k in FIELDS))
for path in sorted(glob.glob("output-storm-*.txt")):
    for block in open(path).read().strip().split("\n\n"):
        mode = re.search(r"mode=(\S+)", block)[1]
        extra = re.search(r"STALE_S': '(\d+)'", block)
        label = mode + (f" {extra[1]}s" if extra else "")
        label += " slow 2%" if "'TAIL_P': '0.02'" in block else ""
        print(f"{label:<28}" + "".join(
            f"{re.search(rx, block)[1]:>9}" for rx in FIELDS.values()))
