"""Run Claude Code headless on the task grid, grade each run, keep everything.

Uses the Claude Code subscription the `claude` CLI is logged in with (no API
key). Resumable: finished runs are skipped. Stops at the first run that fails
for an infrastructure reason (usage limit, auth, crash), without recording it.

    python run.py --models haiku sonnet opus fable --repeats 1 --limit 15   # calibration
    python run.py --models haiku --limit 30          # next 30 Haiku runs
    python run.py --models fable --tiers bug --dry-run
"""

import argparse
import gzip
import json
import random
import shutil
import subprocess
import time
from collections import Counter

from common import MODELS, RESULTS, TIERS, WORK_ROOT, build_start, git, load_tasks, tool_env
from grade import grade_repo

ALLOWED = ["Read", "Edit", "Write", "MultiEdit", "Glob", "Grep", "TodoWrite", "Task",
           "Bash(python:*)", "Bash(python3:*)", "Bash(pytest:*)", "Bash(ruff:*)", "Bash(mypy:*)",
           "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)",
           "Bash(rg:*)", "Bash(find:*)", "Bash(wc:*)", "Bash(sed:*)", "Bash(git diff:*)",
           "Bash(git status:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(cd *)",
           "Bash(echo *)",
           # Agents often prefix an environment variable (PYTHONPATH=src python3 ...),
           # which a plain prefix rule does not match; refused commands would handicap them.
           "Bash(PYTHONPATH=* python *)", "Bash(PYTHONPATH=* python3 *)",
           "Bash(PYTHONPATH=* pytest *)", "Bash(PYTHONPATH=* mypy *)"]
DISALLOWED = ["WebFetch", "WebSearch", "CronCreate", "CronDelete", "CronList", "DesignSync",
              "ListAgents", "Monitor", "EnterWorktree", "ExitWorktree", "SendMessage",
              "PushNotification", "RemoteTrigger"]
SEED = 20261114


def plan(models, task_ids, tiers, repeats) -> list[tuple]:
    tasks = [t for t in load_tasks() if (not task_ids or t.id in task_ids)
             and (not tiers or t.tier in tiers)]
    # Repeat by repeat, shuffled within each, so a partial batch covers every
    # model and task evenly and no model is run at a systematically different time.
    rng = random.Random(SEED)
    ordered = []
    for repeat in range(1, repeats + 1):
        chunk = [(model, task, repeat) for model in models for task in tasks]
        rng.shuffle(chunk)
        ordered += chunk
    return [(f"{model}-{task.id}-r{repeat}", model, task, repeat)
            for model, task, repeat in ordered]


def summarise_transcript(events: list[dict]) -> dict:
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tools, bash = Counter(), []
    for event in events:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[block["name"]] += 1
                if block["name"] == "Bash":
                    bash.append(block.get("input", {}).get("command", ""))
    return {
        "model_id": init.get("model"),
        "claude_code_version": init.get("claude_code_version"),
        "subtype": result.get("subtype"),
        "is_error": result.get("is_error"),
        "final_text": result.get("result") or "",
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "duration_api_ms": result.get("duration_api_ms"),
        "api_equivalent_usd": result.get("total_cost_usd"),
        "usage": result.get("usage"),
        "model_usage": result.get("modelUsage"),
        "tool_uses": dict(tools),
        "bash_commands": bash,
        "permission_denials": [d.get("tool_input") for d in result.get("permission_denials") or []],
    }


def run_one(run_id: str, model: str, task, repeat: int, max_turns: int, timeout: int) -> dict | None:
    work = WORK_ROOT / run_id
    build_start(work, task)
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
           "--model", model, "--setting-sources", "project,local", "--strict-mcp-config",
           "--permission-mode", "acceptEdits", "--max-turns", str(max_turns),
           "--allowedTools", *ALLOWED, "--disallowedTools", *DISALLOWED]
    started = time.time()
    try:
        done = subprocess.run(cmd, input=task.prompt, cwd=work, env=tool_env(),
                              capture_output=True, text=True, timeout=timeout)
        stdout, stderr, code = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr, code = "harness timeout", -1
    events = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    info = summarise_transcript(events)

    finished_normally = info["subtype"] in ("success", "error_max_turns") or code == -1
    if not finished_normally:
        aborted = RESULTS / "_aborted" / f"{run_id}-{int(started)}"
        aborted.mkdir(parents=True, exist_ok=True)
        (aborted / "stdout.jsonl").write_text(stdout)
        (aborted / "stderr.txt").write_text(stderr)
        shutil.rmtree(work, ignore_errors=True)
        print(f"  aborted: exit {code}, subtype {info['subtype']}: "
              f"{(info['final_text'] or stderr).strip()[:200]}")
        return None

    verdict = grade_repo(work, task)
    out = RESULTS / run_id
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "transcript.jsonl.gz", "wt") as handle:
        handle.write(stdout)
    (out / "diff.patch").write_text(git(work, "diff", "--cached", "HEAD"))
    (out / "final.txt").write_text(info.pop("final_text"))
    meta = {"run_id": run_id, "task": task.id, "tier": task.tier, "repeat": repeat,
            "model_alias": model, "prompt": task.prompt, "harness_timeout": code == -1,
            "wall_s": round(time.time() - started, 1), **info, "grade": verdict}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    shutil.rmtree(work, ignore_errors=True)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    parser.add_argument("--tasks", nargs="*", default=[])
    parser.add_argument("--tiers", nargs="*", default=[], choices=TIERS)
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--limit", type=int, default=10, help="new runs in this batch")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=1200, help="seconds per run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    todo = [p for p in plan(args.models, args.tasks, args.tiers, args.repeats)
            if not (RESULTS / p[0] / "meta.json").exists()]
    print(f"{len(todo)} run(s) left; this batch: {min(args.limit, len(todo))}")
    if args.dry_run:
        for run_id, *_ in todo[:args.limit]:
            print(" ", run_id)
        return
    for run_id, model, task, repeat in todo[:args.limit]:
        print(f"{run_id} ...", flush=True)
        meta = run_one(run_id, model, task, repeat, args.max_turns, args.timeout)
        if meta is None:
            print("stopping: fix the cause (or wait for the usage window) and rerun; "
                  "finished runs are kept")
            return
        g = meta["grade"]
        extra = f" kills={g['kills']}/{g['mutants']}" if "kills" in g else ""
        print(f"  {g['outcome']:<5} {'; '.join(g['reasons'])}{extra}  model={meta['model_id']} "
              f"turns={meta['num_turns']} {meta['wall_s']}s "
              f"~${meta['api_equivalent_usd'] or 0:.2f} equiv"
              f"  denied={len(meta['permission_denials'])}", flush=True)


if __name__ == "__main__":
    main()
