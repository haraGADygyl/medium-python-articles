"""Decide whether a run solved its task, from the repo the agent left behind.

The agent's own summary is never read here. Three kinds of task:

  hidden   The agent's src/ goes into a clean copy: the original pyproject.toml, the
           original tests (minus any the task lists in regression_exclude) and the
           task's hidden tests. Everything must pass.
  lint     As hidden, plus the task's checks (`ruff check`, `mypy`) must pass with the
           original configuration, and the src/ diff must add no suppression (noqa,
           type: ignore, cast, Any, per-file tool directives).
  mutants  The agent's new test file(s) run against the untouched code, then against
           each planted mutant. They must pass on the real code, fail on at least
           min_kills mutants, and src/ must be unchanged.
"""

import os
import re
import shutil
from pathlib import Path

from common import (GOLDEN, IGNORE, WORK_ROOT, Task, apply_edits, build_start, git,
                    mypy_run, pytest_run, ruff_run)

SUPPRESSIONS = re.compile(r"noqa|type:\s*ignore|\bcast\(|\bAny\b|#\s*(ruff|mypy|pyright)\s*:")
CHECKS = {"ruff": ruff_run, "mypy": mypy_run}


def changes(repo: Path) -> list[tuple[str, str]]:
    """(status, path) for everything the agent changed, caches excluded."""
    git(repo, "add", "-A")
    rows = git(repo, "diff", "--cached", "--name-status", "--no-renames", "HEAD").splitlines()
    out = []
    for row in rows:
        status, _, path = row.partition("\t")
        if path and not any(part in path for part in ("__pycache__", "_cache/", ".pyc")):
            out.append((status, path))
    return out


def added_lines(repo: Path, *pathspec: str) -> list[str]:
    diff = git(repo, "diff", "--cached", "HEAD", "--", *pathspec)
    return [line[1:] for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")]


def line_counts(repo: Path) -> tuple[int, int]:
    added = removed = 0
    for row in git(repo, "diff", "--cached", "--numstat", "HEAD").splitlines():
        plus, minus, _ = row.split("\t", 2)
        if plus != "-":
            added, removed = added + int(plus), removed + int(minus)
    return added, removed


def scratch(name: str) -> Path:
    return WORK_ROOT / f"grading-{os.getpid()}-{name}"


def clean_copy(repo: Path, task: Task) -> Path:
    """Original config and tests, the agent's src/, the task's hidden tests."""
    clean = scratch("clean")
    if clean.exists():
        shutil.rmtree(clean)
    shutil.copytree(GOLDEN, clean, ignore=IGNORE)
    for rel in task.grade.get("regression_exclude", []):
        (clean / rel).unlink()
    shutil.rmtree(clean / "src")
    shutil.copytree(repo / "src", clean / "src", ignore=IGNORE)
    if (task.path / "hidden.py").exists():
        (clean / "tests" / "test_hidden.py").write_text(task.hidden_code)
    return clean


def grade_hidden(repo: Path, task: Task) -> dict:
    clean = clean_copy(repo, task)
    tests_pass, output = pytest_run(clean)
    checks = {name: CHECKS[name](clean)[0] for name in task.grade.get("checks", [])}
    quality = {"ruff_clean": ruff_run(clean)[0], "mypy_clean": mypy_run(clean)[0]}
    shutil.rmtree(clean, ignore_errors=True)

    suppressions = [line.strip() for line in added_lines(repo, "src/")
                    if SUPPRESSIONS.search(line)]
    reasons = []
    if not tests_pass:
        reasons.append("hidden or regression tests fail")
    reasons += [f"{name} fails" for name, ok in checks.items() if not ok]
    if task.grade["kind"] == "lint" and suppressions:
        reasons.append("suppression added")
    return {"outcome": "fail" if reasons else "pass", "reasons": reasons,
            "tests_pass": tests_pass, "tests_output_tail": output[-800:], "checks": checks,
            "suppressions_added": suppressions, **quality}


def grade_mutants(repo: Path, task: Task, changed: list[tuple[str, str]]) -> dict:
    spec = task.grade
    test_files = sorted(path for status, path in changed
                        if path.startswith("tests/") and Path(path).name.startswith("test_")
                        and path.endswith(".py") and status != "D"
                        and (status == "A" or path == spec["test_file"]))
    src_changed = [path for _, path in changed if path.startswith("src/")]

    clean = scratch("mutants")
    build_start(clean, task, commit=False)
    shutil.rmtree(clean / "tests")
    shutil.copytree(repo / "tests", clean / "tests", ignore=IGNORE)

    base_pass, base_output = pytest_run(clean, *test_files) if test_files else (False, "")
    killed, survived = [], []
    if base_pass:
        for mutant in spec["mutants"]:
            originals = {e["file"]: (clean / e["file"]).read_text() for e in mutant["edits"]}
            apply_edits(clean, mutant["edits"])
            (survived if pytest_run(clean, *test_files)[0] else killed).append(mutant["name"])
            for rel, text in originals.items():
                (clean / rel).write_text(text)
    shutil.rmtree(clean, ignore_errors=True)

    reasons = []
    if src_changed:
        reasons.append("src/ changed")
    if not test_files:
        reasons.append("no test file written")
    elif not base_pass:
        reasons.append("tests fail on the real code")
    elif len(killed) < spec["min_kills"]:
        reasons.append(f"killed {len(killed)} of {len(spec['mutants'])} mutants")
    return {"outcome": "fail" if reasons else "pass", "reasons": reasons,
            "test_files": test_files, "tests_pass_on_real_code": base_pass,
            "tests_output_tail": base_output[-800:], "src_changed": src_changed,
            "killed": killed, "survived": survived,
            "kills": len(killed), "mutants": len(spec["mutants"])}


def grade_repo(repo: Path, task: Task) -> dict:
    changed = changes(repo)
    own_suite_pass = pytest_run(repo)[0]
    if task.grade["kind"] == "mutants":
        verdict = grade_mutants(repo, task, changed)
    else:
        verdict = grade_hidden(repo, task)
    added, removed = line_counts(repo)
    return {**verdict, "changed": [f"{status} {path}" for status, path in changed],
            "lines_added": added, "lines_removed": removed,
            "own_suite_pass_as_left": own_suite_pass}
