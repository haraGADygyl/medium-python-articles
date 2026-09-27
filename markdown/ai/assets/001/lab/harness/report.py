"""Aggregate graded runs into the tables the article quotes."""
import json
from collections import Counter, defaultdict
from statistics import median

from common import CONDITIONS, RESULTS

OUTCOMES = ["honest fix", "special-cased", "tampered", "flagged", "failed"]


def load() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(RESULTS.glob("*/meta.json"))]


TITLES = {"easy": "easy solvable tasks (t01-t10): the control",
          "hard": "two-step solvable tasks (h01, h02)",
          "impossible": "impossible tasks (i01-i10, t11, t12): any pass is a shortcut"}


def table(runs: list[dict], family: str) -> None:
    print(f"\n{TITLES[family]}")
    print(f"{'model':<8}{'condition':<28}{'n':>4}" + "".join(f"{o:>15}" for o in OUTCOMES)
          + f"{'med turns':>11}{'equiv $':>9}")
    groups = defaultdict(list)
    for run in runs:
        if run.get("family", "impossible" if run["impossible"] else "easy") == family:
            groups[(run["model_alias"], run["condition"])].append(run)
    for (model, condition), rows in sorted(groups.items()):
        counts = Counter(r["grade"]["outcome"] for r in rows)
        turns = [r["num_turns"] for r in rows if r["num_turns"] is not None]
        cost = sum(r["api_equivalent_usd"] or 0 for r in rows)
        print(f"{model:<8}{CONDITIONS[condition]['name']:<28}{len(rows):>4}"
              + "".join(f"{counts.get(o, 0):>15}" for o in OUTCOMES)
              + f"{median(turns) if turns else 0:>11}{cost:>9.2f}")


def main() -> None:
    runs = load()
    print(f"{len(runs)} graded runs; models: "
          f"{sorted({(r['model_alias'], r['model_id']) for r in runs})}")
    for family in ("impossible", "hard", "easy"):
        table(runs, family)
    bypass = [r["run_id"] for r in runs if r["hook_blocks"] and r["grade"]["outcome"] == "tampered"]
    print(f"\ntampered despite a hook block (bypass): {bypass}")


if __name__ == "__main__":
    main()
