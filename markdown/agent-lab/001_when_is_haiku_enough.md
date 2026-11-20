# When Is Haiku Enough? I Ran Four Claude Models 304 Times to Find Out

#### Haiku matched Opus and Fable on every refactor and bug fix at a fraction of the cost. It fell behind only when making the type checker happy meant breaking what the README promised

**By Tihomir Manushev**

*Nov 18, 2026 · 8 min read*

---

Most people who use an AI coding agent run the biggest model for everything: a rename, a lint fix, a one-line bug. It feels safe. It is also the most expensive choice, and on a subscription it uses up your limits fastest.

So the question is practical. On ordinary coding work, where does the cheapest Claude model tie the expensive ones, and where does it fall behind? I built a small project nobody had seen, wrote fifteen tasks of the kind developers hand to agents every day, and ran Claude Code on them with four models: Claude Haiku 5.5, Sonnet 5.5, Opus 5.5 and Fable 5.2.

Haiku passed every refactor, every bug fix and every two-file bug, four runs out of four, at about one forty-seventh of Fable's cost. Nearly every failure of the cheaper models came from one situation. The request was narrow ("make the type checker pass"), and the README promised something the narrow fix broke. Opus and Fable never got that wrong. Haiku and Sonnet usually did, and they said so in their own reports.

---

### The test project

The project is `trailhead`, a 379-line Python package I wrote for this experiment. It plans hikes from recorded GPS tracks: distance, ascent, walking time by Naismith's rule, and how to split a long walk into days. It has 47 tests, passes `ruff` and `mypy --strict`, and has a README that states what the code must do. One of those promises is about the compass heading in a track summary:

```markdown
- **Heading** in the summary is the compass point (N, NE, E, SE, S, SW, W, NW) from the
  start to the finish, or `loop` when the finish is within 0.1 km of the start.
```

That one sentence turned out to decide most of the results.

---

### Fifteen tasks, five kinds

I wrote three tasks for each of five kinds of work: a refactor or small feature, writing tests, fixing lint and type errors, a bug in one file, and a bug that needs fixing in two files. Each kind has one easy **baseline** task and two harder ones. A first calibration run of 60 showed that easy tasks alone separate nothing: 58 of 60 passed. So each harder task hides a trap. Some examples:

- Cache the leg lengths of a `Track`, which the README says can be changed in place. A naive cache goes stale.
- Add Tobler's hiking function as a second pace model across four files. A descent must not be timed like a climb.
- A bug report says the summary shows `0h 44m` for a 44.9-minute walk. The same truncation is copied into a second file that the report never mentions.
- Garmin exports fail on the header line. The cause is an invisible byte-order mark at the start of the file.

Bug tasks arrive the way users write them, with no file names and no failing test. The project's own tests are green at the start, so the agent has to find the cause itself.

---

### The task that split them

One lint task starts from a version of the project where `mypy` reports three errors. The request is short:

```text
`mypy` (strict mode, configured in `pyproject.toml`) reports errors in `src/`. Fix them so
that `mypy` passes, without `# type: ignore`, `cast`, `Any`, or changes to the mypy configuration.
```

Two of the errors are routine: a function with no type annotations, and a call to it from typed code. The third comes from this function, planted for the task:

```python
def _heading(track: Track) -> str | None:
    start, finish = track.points[0], track.points[-1]
    if haversine_km(start.lat, start.lon, finish.lat, finish.lon) <= LOOP_RADIUS_KM:
        return None
    return compass_point(initial_bearing(start.lat, start.lon, finish.lat, finish.lon))
```

For a circular walk it returns `None`, but the `Summary` it feeds declares `heading: str`, so `mypy` complains:

```text
src/trailhead/report.py:53: error: Argument "heading" to "Summary" has incompatible type "str | None"; expected "str"  [arg-type]
```

There are two ways to make that error go away. Widen the field to `str | None`, and loops print `heading   None` in every summary. Or return `"loop"`, which is what the README promises. Both satisfy `mypy`. Only one keeps the promise.

A second task works the same way. Elevations became optional, because GPS units lose them, and `mypy` now flags every place that does arithmetic on one. The README says a missing elevation takes the previous point's value. Skipping those points also silences `mypy`, but it reports a 9% climb as flat.

---

### How each run was judged

Every run started from a fresh copy of the project and a clean Claude Code session: no personal settings, no web access, at most 40 steps, inside Claude Code's sandbox, which blocks the network and any write outside the project. The runner pipes the request into Claude Code's non-interactive mode, through my subscription:

```bash
claude -p --model haiku --output-format stream-json --verbose \
  --setting-sources project,local --strict-mcp-config \
  --permission-mode acceptEdits --max-turns 40 \
  --settings '{"sandbox": {"enabled": true, "autoAllowBashIfSandboxed": true}}' < prompt.txt
```

The agent's summary was never trusted. Its code went into a clean copy of the project with **hidden tests** it never saw. For the heading task, one of them is:

```python
def test_loop_heading_is_loop(make_track):
    summary = summarise(make_track(*LOOP, name="Lake Circuit"))
    assert summary.heading in ("loop", None)
    assert format_summary(summary).endswith("\n  heading   loop")
```

Test-writing tasks were graded differently. I planted seven to nine small bugs, called **mutants**, one at a time. The agent's tests had to catch all but one of them. Lint tasks also had to pass the checker with no suppression comments added. Each model ran each task four times, which makes 240 runs. Afterwards I ran the two lint tasks that split the models eight more times each, for 12 runs per model.

---

### The results

```text
                                   Haiku 5.5   Sonnet 5.5   Opus 5.5   Fable 5.2
refactor / small feature (12)          12          12          12          12
writing tests (12)                     11          12          12          12
lint and type errors (12)               8           7          12          12
bug in one file (12)                   12          12          12          12
bug in two files (12)                  12          12          12          12
all tasks (60)                         55          55          60          60

heading task, 12 runs                   0           4          12          12
missing-elevation task, 12 runs         8           4          12          12

API-equivalent cost of 60 runs       $0.66       $6.19      $15.82      $31.01
wall-clock time of 60 runs          43 min      26 min      48 min      49 min
median steps, harder tasks             13           7           8           6
```

The costs are Claude Code's own estimates of what the runs would cost through the API. My subscription was not billed for them.

On 13 of the 15 tasks, Haiku did what the biggest model did. It found the copied truncation in the second file, noticed the invisible byte-order mark, and kept the cache honest when points changed. It took about twice as many steps to get there, but each step cost very little. Sonnet was the fastest model by wall-clock time.

The failures are almost all on the two lint tasks. Here is Sonnet's change in a run that failed the heading task:

```diff
-    heading: str
+    heading: str | None
```

And here is Opus's change in a run that passed:

```diff
-def _heading(track: Track) -> str | None:
+def _heading(track: Track) -> str:
     start, finish = track.points[0], track.points[-1]
     if haversine_km(start.lat, start.lon, finish.lat, finish.lon) <= LOOP_RADIUS_KM:
-        return None
+        return "loop"
```

---

### They knew, and said so

What surprised me is that the failing models were not careless. All 20 runs that failed the heading task reported in their final message that loops would now print `None`, and 15 of them offered to change it as a follow-up instead of doing it. Sonnet: "I left that alone because you asked only for the type errors." Haiku: "the `None` for loops is intentional." None of the 20 mentions the README. Even among Sonnet's four passes, only one cited it. Two called `loop` their own wording: "I chose the wording 'loop' myself."

The missing-elevation task looks the same. None of the 12 failures mentioned the README, and 11 described their gap handling as their own choice. Sonnet wrote: "The gap-handling rules are my choice, not something the repo specified." The README specified them in one paragraph. One Haiku run made a missing elevation an error, and explained, "I didn't pick one silently."

---

### Why the narrow request matters

The transcripts show what separated the passes from the failures: whether the agent opened the README at all. On the missing-elevation task, all 36 passing runs read it, whichever model they came from, and none of the 12 failing runs did. On the heading task, Fable read it in all 12 runs and Opus in 8. Haiku and Sonnet read it in only 3 of their 20 failures. I counted a run as reading the README when one of its tool calls named the file.

The runs that skipped it took "make `mypy` pass" as the whole job, and treated the code as the description of what was intended. The function returned `None` for loops, so `None` must be intended, and the type was what was wrong.

The bug reports, by contrast, describe a symptom the user wants gone, so the target is clear. That is where Haiku tied everyone.

---

### What to copy

For refactors, bug reports and test writing on a project of this size, Haiku was enough in every run of this lab, and it cost cents. Use the bigger model when the request is about satisfying a tool, such as a type checker, a linter or a failing check, and the project documents behaviour the tool knows nothing about.

When you do use a cheaper model, read the last paragraph of its report. All 32 failures on the two lint tasks described their shortcut there, in a sentence like this:

```text
`format_summary` still prints `heading   None` for loop tracks, as it did before. I left that
alone because you asked only for the type errors.
```

That sentence is the bug report.

---

### What this does and does not show

This is one 379-line project, four models and four runs per task, extended to twelve for two tasks. Treat the numbers as strong signals, not rates. Claude Code updated itself from 2.1.325 to 2.1.326 before the extra runs, but every model got all of its extra runs on the same version. After reading the transcripts I corrected two grading mistakes and regraded every run from its saved changes, without running any agent again. Four failures became passes as a result. Claude Code still refused 115 shell commands it could not analyse, mostly Fable's and Haiku's, but none of the failed runs had a refused command. I did not test whether telling a cheaper model to follow the README closes the gap. That is the next experiment. The project, all fifteen tasks, the grader and all 304 transcripts are [on GitHub](https://github.com/haraGADygyl/medium-python-articles/tree/main/markdown/agent-lab/assets/001/lab).

---

### Conclusion

On routine coding work, the cheapest Claude model was not the risk. Haiku fixed every bug, refactored safely and wrote tests nearly as thorough as Opus's, for well under a dollar across 60 runs.

The gap between models appeared in one place: where the request was narrower than the project's promises. There, Haiku and Sonnet did exactly what they were asked, left the promise broken, and told me so in their reports. Opus and Fable kept the promise every time.

So route by task, not by habit. Give the routine work to the cheap model, and give the "make the tool happy" work to a bigger one. Whichever model you use, read its report to the end.
