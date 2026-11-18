# Lab: agent-lab/001, when is Haiku enough?

Four Claude models get the same routine coding tasks in Claude Code: Haiku 5.5, Sonnet 5.5,
Opus 5.5 and Fable 5.2. The lab measures where the cheap model ties the expensive ones and
where it falls behind. The pitch is in `rules/agent-lab/LIST.md` #2 in the articles-writer
repo. This lab's harness is the one batch 2 (#3–#11) reuses.

## Layout

| Path | What it is |
| --- | --- |
| `trailhead/` | The golden repo: a small Python 3.12 hiking planner (379 lines: track parsing, distance, ascent, Naismith time, day plans, summary, CLI), a README contract, 47 passing tests, clean under `ruff` and `mypy --strict` (ascent rule shared by summary and plan, settings apply to the whole file) |
| `tasks/<id>/task.json` | The prompt, the setup edits that turn the golden repo into the task (string edits, deletions, attached files), whether it is a baseline task, the grading spec, a reference solution and a sample bad solution |
| `tasks/<id>/hidden.py` | Tests the agent never sees (hidden and lint tasks) |
| `tasks/<id>/reference_test.py`, `weak_test.py` | A test file that kills every mutant, and a happy-path one that should not pass (tests tasks) |
| `harness/common.py` | Models, tiers, building working copies, pytest/ruff/mypy runners |
| `harness/make_tasks.py` | Writes every `task.json`; edit it and regenerate rather than hand-editing JSON |
| `harness/verify.py` | Proves every task is well-formed, with no model calls |
| `harness/run.py` | Runs `claude -p` over the grid, resumable, and grades each run |
| `harness/grade.py` | Decides pass/fail from the repo the agent left behind |
| `harness/report.py` | The tables the article quotes |
| `runs/<model>-<task>-r<n>/` | One folder per run: `meta.json` (metrics and grade), `diff.patch`, `final.txt`, `transcript.jsonl.gz` |
| `runs/_smoke/`, `runs/_aborted/`, `runs/_calibration/` | Harness shake-down runs, infrastructure failures, and the first calibration on the old task set, all excluded from results |

## Tasks: 15, three per tier

A first calibration (60 runs, in `runs/_calibration/`) gave 58 passes out of 60. The tasks were
too easy to separate the models. Each tier now keeps one **baseline** task that every model
passed in calibration and adds two **harder** ones. Most of the harder tasks hide a trap
where the obvious change satisfies the prompt but breaks the README contract.

| Tier | Task | | What the agent is asked | The trap |
| --- | --- | --- | --- | --- |
| refactor/feature | r01 | baseline | rename `haversine_km` → `distance_km`, keep a deprecated alias | none to speak of |
| refactor/feature | r04 | harder | cache leg lengths so a summary computes each once | `Track.points` is mutable (README): the cache must notice appends, replacement and in-place edits, must not leak its list, and must keep `==`/`repr` |
| refactor/feature | r05 | harder | add Tobler as a `pace` option to `leg_hours`, `split_days`, `summarise` and the CLI | signed grade (downhill differs from uphill), zero-length legs, fitness, invalid values, four files |
| tests | t02 | baseline | write tests for `pace.py` | 8 mutants |
| tests | t04 | harder | write tests for `plan.py` | 9 mutants, including a day that exactly fills the limit and truncated minutes |
| tests | t05 | harder | write tests for `report.py` | 9 mutants, including loop radius, reversed heading and threshold plumbing |
| lint | l01 | baseline | make `ruff check` pass | the "unused" `hours` is the fitness maths |
| lint | l02 | harder | make `mypy --strict` pass | `_heading` returns `None` for loops; the README says `loop` (the only task that separated models in calibration) |
| lint | l04 | harder | make `mypy --strict` pass after elevations became optional | `p.ele or 0.0` silences mypy but reads lost elevations as sea level; the README says fill from the previous point |
| bug | b01 | baseline | report: a 300 m climb in 1 m steps shows +0 m | ascent threshold without hysteresis |
| bug | b04 | harder | report: Garmin exports fail on the header (file attached) | a UTF-8 byte-order mark; stripping it only at the header check fails when a comment comes first |
| bug | b05 | harder | report: `# units: ft` at the end of the file is ignored (file attached) | units must apply to the whole track, wherever the line is |
| two-file bug | h03 | baseline | report: `steepest_grade` returns 0.18, not 18.0 | `report.py` compensates; fixing only `elevation.py` shows 1800% |
| two-file bug | h04 | harder | report: summary shows 0h 44m for 44.9 minutes | the same truncation is copied into `plan.py`, which the report doesn't mention |
| two-file bug | h05 | harder | report: plan days don't add up to the summary on a noisy track | `pace.leg_hours` must credit climbs by the summary's ascent rule (`elevation.counted_changes`) |

Bug prompts are written as user bug reports: no file names and no failing test. The
starting repo's own test suite is always green. Tests that would catch the planted bug are
removed in setup, so the agent has to find the cause itself.

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
allowlist of ordinary development commands (python, pytest, ruff, mypy, git, file
viewing and scratch files, `PYTHONPATH=… python …` forms), with no `rm`, network
tools or sudo. Claude Code's own safety checks still refuse subshells and `cd … && git`.
Refused calls are recorded per run, and the report lists them.

Versions at build time: Claude Code 2.1.325, Python 3.12.3, pytest 9.1.1, ruff 0.17.5,
mypy 2.4.1.
