"""Run Claude Code headless on the task grid, grade each run, keep everything.

Uses the Claude Code subscription the `claude` CLI is logged in with (no API
key). Resumable: finished runs are skipped. Stops at the first run that fails
for an infrastructure reason (usage limit, auth, crash), without recording it.

    python run.py --model opus --limit 10          # next 10 runs of the Opus grid
    python run.py --model sonnet --conditions 1 5  # Sonnet on two conditions
    python run.py --model opus --dry-run           # show what is left
"""
import argparse
import gzip
import json
import os
import random
import shutil
import subprocess
import time
from collections import Counter

from common import (CONDITIONS, RESULTS, WORK_ROOT, build_task_repo, ensure_venv, git,
                    load_tasks, prompt_for)
from grade import grade_repo

ALLOWED = ["Read", "Edit", "Write", "MultiEdit", "Glob", "Grep", "TodoWrite", "Task",
           "Bash(python:*)", "Bash(python3:*)", "Bash(pytest:*)", "Bash(ls:*)", "Bash(cat:*)",
           "Bash(head:*)", "Bash(tail:*)", "Bash(grep:*)", "Bash(rg:*)", "Bash(find:*)",
           "Bash(wc:*)", "Bash(sed:*)", "Bash(git diff:*)", "Bash(git status:*)",
           "Bash(git log:*)", "Bash(git show:*)"]
DISALLOWED = ["WebFetch", "WebSearch", "CronCreate", "CronDelete", "CronList", "DesignSync",
              "ListAgents", "Monitor", "EnterWorktree", "ExitWorktree", "SendMessage",
              "PushNotification", "RemoteTrigger"]
SEED = 20260926


def plan(model: str, task_ids, conditions, repeats, families=()) -> list[tuple]:
    tasks = [t for t in load_tasks() if (not task_ids or t.id in task_ids)
             and (not families or t.family in families)]
    runs = [(t, c, r) for r in range(1, repeats + 1) for c in conditions for t in tasks]
    # Shuffle within each repeat so a partial batch covers every condition evenly
    # and no condition is systematically run at a different time of day.
    rng = random.Random(f"{SEED}-{model}")
    ordered = []
    for r in range(1, repeats + 1):
        chunk = [x for x in runs if x[2] == r]
        rng.shuffle(chunk)
        ordered += chunk
    return [(f"{model}-{t.id}-c{c}-r{r}", t, c, r) for t, c, r in ordered]


def summarise_transcript(events: list[dict]) -> dict:
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tools, bash, blocked = Counter(), [], 0
    for event in events:
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tools[block["name"]] += 1
                if block["name"] == "Bash":
                    bash.append(block.get("input", {}).get("command", ""))
            if block.get("type") == "tool_result" and "Blocked:" in json.dumps(block.get("content")):
                blocked += 1
    return {
        "model_id": init.get("model"),
        "claude_code_version": init.get("claude_code_version"),
        "subtype": result.get("subtype"),
        "is_error": result.get("is_error"),
        "final_text": result.get("result") or "",
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "api_equivalent_usd": result.get("total_cost_usd"),
        "usage": result.get("usage"),
        "tool_uses": dict(tools),
        "bash_commands": bash,
        "hook_blocks": blocked,
    }


def run_one(run_id: str, task, condition: int, repeat: int, model: str,
            max_turns: int, timeout: int) -> dict | None:
    work = WORK_ROOT / run_id
    build_task_repo(work, task, condition)
    prompt = prompt_for(task, condition)
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
           "--model", model, "--setting-sources", "project,local", "--strict-mcp-config",
           "--permission-mode", "acceptEdits", "--max-turns", str(max_turns),
           "--allowedTools", *ALLOWED, "--disallowedTools", *DISALLOWED]
    env = dict(os.environ, PATH=f"{ensure_venv()}:{os.environ['PATH']}")
    started = time.time()
    try:
        done = subprocess.run(cmd, input=prompt, cwd=work, env=env, capture_output=True,
                              text=True, timeout=timeout)
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

    verdict = grade_repo(work, task, info["final_text"])
    out = RESULTS / run_id
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / "transcript.jsonl.gz", "wt") as handle:
        handle.write(stdout)
    (out / "diff.patch").write_text(git(work, "diff", "--cached", "HEAD"))
    (out / "final.txt").write_text(info.pop("final_text"))
    meta = {"run_id": run_id, "task": task.id, "impossible": task.impossible,
            "family": task.family,
            "condition": condition, "condition_name": CONDITIONS[condition]["name"],
            "repeat": repeat, "model_alias": model, "prompt": prompt,
            "harness_timeout": code == -1, "wall_s": round(time.time() - started, 1),
            **info, "grade": verdict}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    shutil.rmtree(work, ignore_errors=True)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="claude --model alias, e.g. opus, sonnet")
    parser.add_argument("--tasks", nargs="*", default=[])
    parser.add_argument("--family", nargs="*", default=[], choices=["easy", "impossible", "hard"])
    parser.add_argument("--conditions", nargs="*", type=int, default=list(CONDITIONS))
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--limit", type=int, default=10, help="new runs in this batch")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--timeout", type=int, default=1200, help="seconds per run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    todo = [p for p in plan(args.model, args.tasks, args.conditions, args.repeats, args.family)
            if not (RESULTS / p[0] / "meta.json").exists()]
    print(f"{len(todo)} run(s) left for {args.model}; this batch: {min(args.limit, len(todo))}")
    if args.dry_run:
        for run_id, *_ in todo[:args.limit]:
            print(" ", run_id)
        return
    for run_id, task, condition, repeat in todo[:args.limit]:
        print(f"{run_id} ...", flush=True)
        meta = run_one(run_id, task, condition, repeat, args.model, args.max_turns, args.timeout)
        if meta is None:
            print("stopping: fix the cause (or wait for the usage window) and rerun; "
                  "finished runs are kept")
            return
        g = meta["grade"]
        print(f"  {g['outcome']:<14} turns={meta['num_turns']} {meta['wall_s']}s "
              f"~${meta['api_equivalent_usd'] or 0:.2f} equiv  hook_blocks={meta['hook_blocks']}"
              f"  changed={g['changed_paths']}", flush=True)


if __name__ == "__main__":
    main()
