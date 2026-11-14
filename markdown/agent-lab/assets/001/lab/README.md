# Lab: agent-lab/001, when is Haiku enough?

Four Claude models get the same routine coding tasks in Claude Code: Haiku 5.5, Sonnet 5.5,
Opus 5.5 and Fable 5.2. The lab measures where the cheap model ties the expensive ones and
where it falls behind. The pitch is in `rules/agent-lab/LIST.md` #2 in the articles-writer
repo. This lab's harness is the one batch 2 (#3–#11) reuses.

## Layout

| Path | What it is |
| --- | --- |
| `trailhead/` | The golden repo: a small Python 3.12 hiking planner (track parsing, distance, ascent, Naismith time, day plans, summary, CLI), a README contract, 47 passing tests, clean under `ruff` and `mypy --strict` |
| `tasks/<id>/task.json` | The prompt, the setup edits that turn the golden repo into the task, the grading spec, a reference solution and a sample bad solution |
| `tasks/<id>/hidden.py` | Tests the agent never sees (hidden and lint tasks) |
| `tasks/<id>/reference_test.py`, `weak_test.py` | A test file that kills every mutant, and a happy-path one that should not pass (tests tasks) |
| `harness/common.py` | Models, tiers, building working copies, pytest/ruff/mypy runners |
| `harness/make_tasks.py` | Writes every `task.json`; edit it and regenerate rather than hand-editing JSON |
| `harness/verify.py` | Proves every task is well-formed, with no model calls |
| `harness/run.py` | Runs `claude -p` over the grid, resumable, and grades each run |
| `harness/grade.py` | Decides pass/fail from the repo the agent left behind |
| `harness/report.py` | The tables the article quotes |
| `runs/<model>-<task>-r<n>/` | One folder per run: `meta.json` (metrics and grade), `diff.patch`, `final.txt`, `transcript.jsonl.gz` |
| `runs/_smoke/`, `runs/_aborted/` | Harness shake-down runs and infrastructure failures, excluded from results |

## Tasks: 15, three per tier

| Tier | Task | What the agent is asked | What makes it hard |
| --- | --- | --- | --- |
| refactor | r01 | rename `haversine_km` → `distance_km`, keep a deprecated alias | the alias must warn, other modules must stop using the old name |
| refactor | r02 | extract duplicated duration formatting into `timefmt.format_duration` | both callers must use it, output byte-identical |
| refactor | r03 | `split_days` tuples → frozen `DayPlan` dataclass | every caller and test unpacks by position |
| tests | t01–t03 | write tests for `elevation.py`, `pace.py`, `track.py` | graded by planted mutants (7, 8, 7); pass = all but one killed |
| lint | l01 | make `ruff check` pass | the "unused variable" `hours` is the fitness calculation; deleting it breaks fitness |
| lint | l02 | make `mypy --strict` pass | `_heading` returns `None` for loops; the README says it should say `loop` |
| lint | l03 | make `mypy --strict` pass | two `None` defaults hide the documented `unnamed` name and 7-hour day |
| bug | b01 | issue: a 300 m climb in 1 m steps shows +0 m | ascent threshold without hysteresis |
| bug | b02 | issue: a due-east ridge is reported as heading N | `atan2` arguments swapped |
| bug | b03 | issue: `--max-hours 6` gives a 6h 50m day | day closes after going over the limit |
| two-file bug | h01 | issue: `plan --fitness` changes nothing | fitness dropped in both `cli.py` and `plan.py` |
| two-file bug | h02 | issue: `--threshold 0` ignored, `0.5` rejected | `threshold or default` in `report.py`, `type=int` in `cli.py` |
| two-file bug | h03 | issue: `steepest_grade` returns 0.18, not 18.0 | `report.py` multiplies by 100 to compensate; fixing only `elevation.py` shows 1800% |

Bug and two-file-bug prompts are written as user bug reports: no file names and no
failing test. The starting repo's own test suite is always green. Tests that would catch
the planted bug are removed in setup, so the agent has to find the cause itself.

## Grading (`grade.py`, never the agent's summary)

| Kind | Tasks | Pass rule |
| --- | --- | --- |
| hidden | refactor, bug, two-file bug | the agent's `src/` in a clean copy with the original `pyproject.toml`, the original tests (r03 drops `test_plan.py`, whose tuples it replaces) and the hidden tests: everything passes |
| lint | l01–l03 | as hidden, plus `ruff check` / `mypy` pass with the original config, and the `src/` diff adds no `noqa`, `type: ignore`, `cast(`, `Any` or tool directive |
| mutants | t01–t03 | `src/` unchanged; the agent's new test file passes on the real code and fails on at least all-but-one of the planted mutants |

Every run also records `ruff` and `mypy` status of the agent's `src/`, whether its own
test suite passes as left, lines changed, turns, wall time, tokens, the API-equivalent
cost, tool uses, refused tool calls, and the exact model id and Claude Code version.

## Running

Runs use the Claude Code subscription the `claude` CLI is logged in to, with no API key.
The limit is the plan's usage windows, so run in batches. The runner stops, without
recording, at the first infrastructure failure (usage limit, auth, crash) and resumes
where it left off. Fable and Opus use up the windows fastest.

```bash
cd harness
python verify.py                                             # all 15 tasks must verify
python run.py --repeats 1 --limit 60                         # calibration: every model x task once
python run.py --models haiku sonnet --limit 40               # continue the 240-run grid in batches
python run.py --models opus fable --limit 20
python report.py --save
```

The grid is 4 models × 15 tasks × 4 repeats = 240 runs, shuffled within each repeat so
a partial batch covers every model and task evenly.

Isolation per run: a fresh git repo under `$TRAILHEAD_WORK_ROOT` (default
`/tmp/trailhead-runs`, away from `tasks/`). `--setting-sources project,local` keeps user
settings, hooks and output style out. `--strict-mcp-config` with no servers. Web tools
are disallowed, and runs have `--max-turns 40` and a 20-minute timeout. A shared venv
with pinned `pytest`, `ruff` and `mypy` comes first on `PATH`. Bash is limited to an
allowlist (python, pytest, ruff, mypy, read-only git and file viewing, plus
`PYTHONPATH=… python …` forms). Refused calls are recorded per run, and the report
lists them.

Versions at build time: Claude Code 2.1.325, Python 3.12.3, pytest 9.1.1, ruff 0.17.5,
mypy 2.4.1.
