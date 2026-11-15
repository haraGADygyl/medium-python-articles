"""Re-grade saved runs with the current tasks and grader, without running any agent.

For each run: rebuild the repo the agent received, apply its saved diff.patch, grade it.
The previous grade is kept in meta.json as grade_v<N>; the new one replaces "grade".

    python regrade.py              # every run
    python regrade.py l02 t05      # runs of some tasks
"""

import json
import shutil
import subprocess
import sys

from common import RESULTS, WORK_ROOT, build_start, load_tasks
from grade import grade_repo


def main() -> None:
    wanted = set(sys.argv[1:])
    tasks = {task.id: task for task in load_tasks()}
    changed = 0
    for meta_path in sorted(RESULTS.glob("*/meta.json")):
        if meta_path.parent.name.startswith("_"):
            continue
        meta = json.loads(meta_path.read_text())
        if wanted and meta["task"] not in wanted:
            continue
        task = tasks[meta["task"]]
        work = WORK_ROOT / "regrade"
        build_start(work, task)
        patch = meta_path.parent / "diff.patch"
        if patch.read_text().strip():
            subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)], cwd=work, check=True)
        new = grade_repo(work, task)
        shutil.rmtree(work, ignore_errors=True)
        version = 1 + sum(1 for key in meta if key.startswith("grade_v"))
        meta[f"grade_v{version}"] = meta["grade"]
        meta["grade"] = new
        meta_path.write_text(json.dumps(meta, indent=2))
        old = meta[f"grade_v{version}"]["outcome"]
        if old != new["outcome"]:
            changed += 1
            print(f"{meta['run_id']}: {old} -> {new['outcome']}  {new['reasons']}")
    print(f"{changed} outcome(s) changed")


if __name__ == "__main__":
    main()
