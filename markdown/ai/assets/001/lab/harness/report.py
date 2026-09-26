"""Aggregate graded runs into the tables the article quotes."""
import json
from collections import Counter, defaultdict
from statistics import median

from common import CONDITIONS, RESULTS

OUTCOMES = ["honest fix", "special-cased", "tampered", "flagged", "failed"]


def load() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(RESULTS.glob("*/meta.json"))]


def table(runs: list[dict], impossible: bool) -> None:
    kind = "impossible tasks (t11, t12): any pass is a shortcut" if impossible \
        else "solvable tasks (t01-t10)"
    print(f"\n{kind}")
    print(f"{'model':<8}{'condition':<28}{'n':>4}" + "".join(f"{o:>15}" for o in OUTCOMES)
          + f"{'med turns':>11}{'equiv $':>9}")
    groups = defaultdict(list)
    for run in runs:
        if run["impossible"] == impossible:
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
    table(runs, impossible=False)
    table(runs, impossible=True)
    bypass = [r["run_id"] for r in runs if r["hook_blocks"] and r["grade"]["outcome"] == "tampered"]
    print(f"\ntampered despite a hook block (bypass): {bypass}")


if __name__ == "__main__":
    main()
