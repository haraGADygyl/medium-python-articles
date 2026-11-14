"""The tables the article quotes, computed from runs/*/meta.json only.

    python report.py            # print the tables
    python report.py --save     # also write ../report.txt
"""

import json
import statistics
import sys
from collections import defaultdict

from common import LAB, MODELS, RESULTS, TIERS


def load_runs() -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(RESULTS.glob("*/meta.json"))
            if not path.parent.name.startswith("_")]


def median(values: list[float]) -> str:
    return f"{statistics.median(values):.1f}" if values else "-"


def tokens(run: dict) -> int:
    usage = run.get("usage") or {}
    return sum(usage.get(key) or 0 for key in ("input_tokens", "output_tokens",
                                                "cache_creation_input_tokens",
                                                "cache_read_input_tokens"))


def build() -> str:
    runs = load_runs()
    models = [m for m in MODELS if any(r["model_alias"] == m for r in runs)]
    lines = [f"{len(runs)} graded runs", ""]

    lines.append("Passes by tier (passed / runs)")
    lines.append(f"{'tier':<14}" + "".join(f"{m:>10}" for m in models))
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for run in runs:
        cells[(run["tier"], run["model_alias"])].append(run["grade"]["outcome"] == "pass")
    for tier in [*TIERS, "all"]:
        row = f"{tier:<14}"
        for model in models:
            hits = (sum((cells[(t, model)] for t in TIERS), []) if tier == "all"
                    else cells[(tier, model)])
            row += f"{f'{sum(hits)}/{len(hits)}':>10}"
        lines.append(row)

    lines += ["", "Per task (passed / runs)"]
    lines.append(f"{'task':<6}" + "".join(f"{m:>10}" for m in models))
    by_task: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for run in runs:
        by_task[(run["task"], run["model_alias"])].append(run["grade"]["outcome"] == "pass")
    for task in sorted({run["task"] for run in runs}):
        lines.append(f"{task:<6}" + "".join(
            f"{f'{sum(by_task[(task, m)])}/{len(by_task[(task, m)])}':>10}" for m in models))

    lines += ["", "Mutants killed by the agent's tests (tests tier, total kills / total mutants)"]
    for model in models:
        mine = [r["grade"] for r in runs if r["model_alias"] == model and "kills" in r["grade"]]
        if mine:
            lines.append(f"  {model:<8} {sum(g['kills'] for g in mine)}/"
                         f"{sum(g['mutants'] for g in mine)}")

    lines += ["", "Cost of a run (medians)"]
    lines.append(f"{'model':<8}{'wall s':>9}{'turns':>7}{'tokens k':>10}{'equiv $':>9}"
                 f"{'lines +/-':>11}")
    for model in models:
        mine = [r for r in runs if r["model_alias"] == model]
        lines.append(
            f"{model:<8}{median([r['wall_s'] for r in mine]):>9}"
            f"{median([r['num_turns'] or 0 for r in mine]):>7}"
            f"{median([tokens(r) / 1000 for r in mine]):>10}"
            f"{median([r['api_equivalent_usd'] or 0 for r in mine]):>9}"
            f"{median([r['grade']['lines_added'] + r['grade']['lines_removed'] for r in mine]):>11}")

    lines += ["", "Failure reasons"]
    reasons: dict[tuple[str, str], int] = defaultdict(int)
    for run in runs:
        for reason in run["grade"]["reasons"]:
            reasons[(run["model_alias"], reason)] += 1
    for (model, reason), count in sorted(reasons.items()):
        lines.append(f"  {model:<8} {count:>3}  {reason}")

    denied = [(r["run_id"], len(r.get("permission_denials") or [])) for r in runs
              if r.get("permission_denials")]
    lines += ["", f"Runs with refused tool calls: {len(denied)}"]
    lines += [f"  {run_id}: {count}" for run_id, count in denied]

    ids = sorted({r.get("model_id") or "?" for r in runs})
    versions = sorted({r.get("claude_code_version") or "?" for r in runs})
    lines += ["", f"Model ids: {', '.join(ids)}", f"Claude Code: {', '.join(versions)}",
              "Costs are Claude Code's API-equivalent estimates: equivalent, not billed."]
    return "\n".join(lines)


if __name__ == "__main__":
    text = build()
    print(text)
    if "--save" in sys.argv:
        (LAB / "report.txt").write_text(text + "\n")
