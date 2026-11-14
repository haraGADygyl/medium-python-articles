"""Prove every task is well-formed before any agent runs. No model calls.

For the golden repo: tests, `ruff check` and `mypy` all pass.
For every task:
  - the setup edits apply, and the repo the agent receives has a green test suite;
  - lint tasks: the named check fails on that repo;
  - the untouched repo grades fail (doing nothing never passes);
  - the reference solution grades pass (mutant tasks: it kills every mutant);
  - the sample bad solution grades fail.

    python verify.py            # all tasks
    python verify.py b01 t02    # some
"""

import shutil
import sys

from common import (GOLDEN, WORK_ROOT, apply_change, build_start, load_tasks, mypy_run,
                    pytest_run, ruff_run)
from grade import CHECKS, grade_repo


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'ok ' if ok else 'BAD'} {label}" + (f"  [{detail}]" if detail and not ok else ""))
    return ok


def graded(task, change: dict | None) -> dict:
    work = WORK_ROOT / f"verify-{task.id}"
    build_start(work, task)
    if change is not None:
        apply_change(work, task, change)
    verdict = grade_repo(work, task)
    shutil.rmtree(work, ignore_errors=True)
    return verdict


def main() -> int:
    wanted = set(sys.argv[1:])
    good = True
    print("golden")
    good &= check("tests pass", *pytest_run(GOLDEN))
    good &= check("ruff clean", *ruff_run(GOLDEN))
    good &= check("mypy clean", *mypy_run(GOLDEN))

    for task in load_tasks():
        if wanted and task.id not in wanted:
            continue
        print(f"{task.id} [{task.tier}] {task.title}")
        start = WORK_ROOT / f"verify-{task.id}-start"
        build_start(start, task, commit=False)
        good &= check("starting test suite is green", *pytest_run(start))
        for name in task.grade.get("checks", []):
            ok, output = CHECKS[name](start)
            good &= check(f"{name} fails on the starting repo", not ok, output[-300:])
        shutil.rmtree(start, ignore_errors=True)

        untouched = graded(task, None)
        good &= check("untouched repo fails", untouched["outcome"] == "fail")

        reference = graded(task, task.reference)
        detail = "; ".join(reference["reasons"]) + " " + reference.get("tests_output_tail", "")[-400:]
        good &= check("reference passes", reference["outcome"] == "pass", detail)
        if task.grade["kind"] == "mutants":
            good &= check(f"reference kills all {reference['mutants']} mutants",
                          reference["kills"] == reference["mutants"],
                          f"survived: {reference['survived']}")

        bad = graded(task, task.bad)
        extra = f" ({bad['kills']}/{bad['mutants']} kills)" if "kills" in bad else ""
        good &= check(f"sample bad solution fails: {task.bad['kind']}{extra}",
                      bad["outcome"] == "fail")

    print("\nALL TASKS VERIFY" if good else "\nSOME CHECKS FAILED")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
