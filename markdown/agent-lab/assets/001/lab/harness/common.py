"""Shared pieces: tasks, building working copies, running pytest, ruff and mypy."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
GOLDEN = LAB / "trailhead"
TASKS_DIR = LAB / "tasks"
RESULTS = LAB / "runs"
# Working copies live away from the lab, so an agent browsing its surroundings
# does not stumble on tasks/ and the hidden tests.
WORK_ROOT = Path(os.environ.get("TRAILHEAD_WORK_ROOT", "/tmp/trailhead-runs"))
VENV = WORK_ROOT / "venv"
PINS = ["pytest==9.1.1", "ruff==0.17.5", "mypy==2.4.1"]
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                                "*.pyc")

MODELS = {  # alias passed to `claude --model`, in price order
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
    "fable": "claude-fable-5-2",
}
TIERS = ["refactor", "tests", "lint", "bug", "two-file bug"]


@dataclass
class Task:
    id: str
    path: Path
    tier: str
    title: str
    prompt: str
    setup: list[dict]
    grade: dict
    reference: dict
    bad: dict

    @property
    def hidden_code(self) -> str:
        return (self.path / "hidden.py").read_text()


def load_tasks() -> list[Task]:
    tasks = []
    for folder in sorted(p for p in TASKS_DIR.iterdir() if (p / "task.json").exists()):
        spec = json.loads((folder / "task.json").read_text())
        tasks.append(Task(spec["id"], folder, spec["tier"], spec["title"], spec["prompt"],
                          spec["setup"], spec["grade"], spec["reference"], spec["bad"]))
    return tasks


def apply_edits(root: Path, edits: list[dict]) -> None:
    """Exact, single-occurrence string replacements, or file deletions; fail loudly."""
    for edit in edits:
        if "delete" in edit:
            (root / edit["delete"]).unlink()
            continue
        target = root / edit["file"]
        text = target.read_text()
        count = text.count(edit["old"])
        if count != 1:
            raise ValueError(f"{edit['file']}: expected 1 match, found {count}: {edit['old'][:60]!r}")
        target.write_text(text.replace(edit["old"], edit["new"]))


def apply_change(root: Path, task: Task, change: dict) -> None:
    """Apply a reference or sample-bad solution: restore golden src, copy files, edit."""
    if change.get("restore_src"):
        shutil.rmtree(root / "src")
        shutil.copytree(GOLDEN / "src", root / "src", ignore=IGNORE)
    for dest, source in change.get("files", {}).items():
        (root / dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(task.path / source, root / dest)
    apply_edits(root, change.get("edits", []))


def copy_golden(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(GOLDEN, dest, ignore=IGNORE)


def build_start(dest: Path, task: Task, commit: bool = True) -> None:
    """Golden repo + the task's setup edits, committed, so the grader can diff
    against exactly what the agent received."""
    copy_golden(dest)
    apply_edits(dest, task.setup)
    if commit:
        git(dest, "init", "-q")
        git(dest, "add", "-A")
        git(dest, "-c", "user.name=lab", "-c", "user.email=lab@localhost",
            "commit", "-qm", "task as handed to the agent")


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout


def ensure_venv() -> Path:
    """A shared venv with pinned pytest, ruff and mypy, first on PATH for agents and grading."""
    python = VENV / "bin" / "python"
    if not python.exists():
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        subprocess.run(["python3", "-m", "venv", str(VENV)], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "-q", *PINS], check=True)
    return VENV / "bin"


def tool_env() -> dict[str, str]:
    return dict(os.environ, PATH=f"{ensure_venv()}:{os.environ['PATH']}",
                PYTHONDONTWRITEBYTECODE="1")


def pytest_run(root: Path, *args: str) -> tuple[bool, str]:
    """Run pytest in `root`; returns (all passed and at least one test ran, output tail)."""
    done = subprocess.run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
                          cwd=root, capture_output=True, text=True, env=tool_env(), timeout=300)
    return done.returncode == 0, done.stdout[-2000:]


def ruff_run(root: Path) -> tuple[bool, str]:
    done = subprocess.run(["ruff", "check", "--no-cache", "src"], cwd=root, capture_output=True,
                          text=True, env=tool_env(), timeout=120)
    return done.returncode == 0, done.stdout[-2000:]


def mypy_run(root: Path) -> tuple[bool, str]:
    done = subprocess.run(["mypy", "--cache-dir", os.devnull], cwd=root, capture_output=True,
                          text=True, env=tool_env(), timeout=300)
    return done.returncode == 0, done.stdout[-2000:]
