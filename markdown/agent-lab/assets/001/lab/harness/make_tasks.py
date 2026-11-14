"""Writes tasks/*/task.json: the planted edits, prompts, grading specs and sample solutions.

The JSON files are what the harness reads; this script is how they were made, kept so a
task can be changed and regenerated. Hidden tests and reference files live beside each
task.json and are written by hand.

    python make_tasks.py && python verify.py
"""
import json
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def e(file, old, new):
    return {"file": file, "old": old, "new": new}


def rm_test(file, text):
    return e(file, text, "")


G, T, EL, PA, PL, RE, CLI = ("src/trailhead/geo.py", "src/trailhead/track.py",
    "src/trailhead/elevation.py", "src/trailhead/pace.py", "src/trailhead/plan.py",
    "src/trailhead/report.py", "src/trailhead/cli.py")
RESTORE = {"restore_src": True}
FIX = " Find the cause and fix it."

tasks = {}

# ---------------------------------------------------------------- refactor
tasks["r01_rename_distance"] = dict(
    tier="refactor", title="Rename haversine_km to distance_km with a deprecated alias",
    prompt=("Rename `haversine_km` in `src/trailhead/geo.py` to `distance_km`, and update every "
            "place in `src/` and `tests/` that uses it. Keep `haversine_km` importable from "
            "`trailhead.geo` as a deprecated alias: calling it should emit a `DeprecationWarning` "
            "and return the same result as `distance_km`."),
    setup=[], grade={"kind": "hidden"},
    reference={"edits": [
        e(G, '"""Great-circle geometry on a spherical Earth."""\n\n',
             '"""Great-circle geometry on a spherical Earth."""\n\nimport warnings\n'),
        e(G, "def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n",
             "def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n"),
        e(G, "    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))\n",
             "    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))\n\n\n"
             "def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n"
             '    """Deprecated name for `distance_km`."""\n'
             '    warnings.warn("haversine_km is deprecated; use distance_km", DeprecationWarning,\n'
             "                  stacklevel=2)\n"
             "    return distance_km(lat1, lon1, lat2, lon2)\n"),
        e(T, "from trailhead.geo import haversine_km\n", "from trailhead.geo import distance_km\n"),
        e(T, "[haversine_km(a.lat", "[distance_km(a.lat"),
        e(RE, "from trailhead.geo import compass_point, haversine_km, initial_bearing\n",
              "from trailhead.geo import compass_point, distance_km, initial_bearing\n"),
        e(RE, "    if haversine_km(start.lat", "    if distance_km(start.lat"),
    ]},
    bad={"kind": "renamed without the alias", "edits": [
        e(G, "def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n",
             "def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n"),
        e(T, "from trailhead.geo import haversine_km\n", "from trailhead.geo import distance_km\n"),
        e(T, "[haversine_km(a.lat", "[distance_km(a.lat"),
        e(RE, "from trailhead.geo import compass_point, haversine_km, initial_bearing\n",
              "from trailhead.geo import compass_point, distance_km, initial_bearing\n"),
        e(RE, "    if haversine_km(start.lat", "    if distance_km(start.lat"),
    ]},
)

DIVMOD_PLAN = "        whole, minutes = divmod(round(hours * 60), 60)\n        lines.append(f\"Day {day}: points {first}-{last}, {whole}h {minutes:02d}m\")\n"
DIVMOD_REPORT = "    whole, minutes = divmod(round(summary.hours * 60), 60)\n"
tasks["r02_extract_duration"] = dict(
    tier="refactor", title="Extract the duplicated duration formatting into timefmt.format_duration",
    prompt=("`plan.py` and `report.py` each have their own copy of the code that formats a number "
            "of hours as text like `5h 07m`. Move it into a single function "
            "`format_duration(hours: float) -> str` in a new module `src/trailhead/timefmt.py`, "
            "and make both modules use it. The output must not change."),
    setup=[], grade={"kind": "hidden"},
    reference={"files": {"src/trailhead/timefmt.py": "timefmt.py"}, "edits": [
        e(PL, "from trailhead.pace import leg_hours\n",
              "from trailhead.pace import leg_hours\nfrom trailhead.timefmt import format_duration\n"),
        e(PL, DIVMOD_PLAN,
              "        lines.append(f\"Day {day}: points {first}-{last}, {format_duration(hours)}\")\n"),
        e(RE, "from trailhead.pace import naismith_hours\n",
              "from trailhead.pace import naismith_hours\nfrom trailhead.timefmt import format_duration\n"),
        e(RE, DIVMOD_REPORT, ""),
        e(RE, '            f"  time      {whole}h {minutes:02d}m",\n',
              '            f"  time      {format_duration(summary.hours)}",\n'),
    ]},
    bad={"kind": "only plan.py uses the new function", "files": {"src/trailhead/timefmt.py": "timefmt.py"},
         "edits": [
        e(PL, "from trailhead.pace import leg_hours\n",
              "from trailhead.pace import leg_hours\nfrom trailhead.timefmt import format_duration\n"),
        e(PL, DIVMOD_PLAN,
              "        lines.append(f\"Day {day}: points {first}-{last}, {format_duration(hours)}\")\n"),
    ]},
)

SPLIT_SIG = ("def split_days(\n    track: Track, max_hours_per_day: float = DEFAULT_MAX_HOURS, fitness: float = 1.0\n"
             ") -> list[tuple[int, int, int, float]]:\n")
tasks["r03_dayplan_dataclass"] = dict(
    tier="refactor", title="Replace split_days tuples with a frozen DayPlan dataclass",
    prompt=("`plan.split_days` returns plain tuples `(day, first_point, last_point, hours)` that "
            "callers unpack by position. Make it return instances of a frozen dataclass `DayPlan` "
            "instead, defined in `src/trailhead/plan.py`, with the fields `day`, `first_point`, "
            "`last_point` and `hours` in that order, and update every caller and test. Behaviour and "
            "command output must stay the same."),
    setup=[], grade={"kind": "hidden", "regression_exclude": ["tests/test_plan.py"]},
    reference={"edits": [
        e(PL, "from trailhead.pace import leg_hours\n",
              "from dataclasses import dataclass\n\nfrom trailhead.pace import leg_hours\n"),
        e(PL, "DEFAULT_MAX_HOURS = 7.0\n",
              "DEFAULT_MAX_HOURS = 7.0\n\n\n@dataclass(frozen=True, slots=True)\nclass DayPlan:\n"
              "    day: int\n    first_point: int\n    last_point: int\n    hours: float\n"),
        e(PL, ") -> list[tuple[int, int, int, float]]:\n", ") -> list[DayPlan]:\n"),
        e(PL, "    days: list[tuple[int, int, int, float]] = []\n", "    days: list[DayPlan] = []\n"),
        e(PL, "            days.append((len(days) + 1, first, index, round(used, 2)))\n",
              "            days.append(DayPlan(len(days) + 1, first, index, round(used, 2)))\n"),
        e(PL, "    days.append((len(days) + 1, first, len(track.points) - 1, round(used, 2)))\n",
              "    days.append(DayPlan(len(days) + 1, first, len(track.points) - 1, round(used, 2)))\n"),
        e(PL, "def describe_plan(days: list[tuple[int, int, int, float]]) -> list[str]:\n",
              "def describe_plan(days: list[DayPlan]) -> list[str]:\n"),
        e(PL, "    for day, first, last, hours in days:\n        whole, minutes = divmod(round(hours * 60), 60)\n"
              "        lines.append(f\"Day {day}: points {first}-{last}, {whole}h {minutes:02d}m\")\n",
              "    for plan in days:\n        whole, minutes = divmod(round(plan.hours * 60), 60)\n"
              "        lines.append(\n            f\"Day {plan.day}: points {plan.first_point}-{plan.last_point}, \"\n"
              "            f\"{whole}h {minutes:02d}m\"\n        )\n"),
    ]},
    bad={"kind": "split_days changed, describe_plan still unpacks tuples", "edits": [
        e(PL, "from trailhead.pace import leg_hours\n",
              "from dataclasses import dataclass\n\nfrom trailhead.pace import leg_hours\n"),
        e(PL, "DEFAULT_MAX_HOURS = 7.0\n",
              "DEFAULT_MAX_HOURS = 7.0\n\n\n@dataclass(frozen=True, slots=True)\nclass DayPlan:\n"
              "    day: int\n    first_point: int\n    last_point: int\n    hours: float\n"),
        e(PL, "            days.append((len(days) + 1, first, index, round(used, 2)))\n",
              "            days.append(DayPlan(len(days) + 1, first, index, round(used, 2)))\n"),
        e(PL, "    days.append((len(days) + 1, first, len(track.points) - 1, round(used, 2)))\n",
              "    days.append(DayPlan(len(days) + 1, first, len(track.points) - 1, round(used, 2)))\n"),
    ]},
)

# ---------------------------------------------------------------- tests (mutation-graded)
def tests_task(module, title, mutants):
    return dict(
        tier="tests", title=title,
        prompt=(f"`src/trailhead/{module}.py` has no tests. Write `tests/test_{module}.py` with pytest "
                "tests that check its behaviour as documented in the README and the docstrings. "
                "Don't change anything under `src/`."),
        setup=[{"delete": f"tests/test_{module}.py"}],
        grade={"kind": "mutants", "test_file": f"tests/test_{module}.py",
               "min_kills": len(mutants) - 1,
               "mutants": [{"name": name, "edits": edits} for name, edits in mutants]},
        reference={"files": {f"tests/test_{module}.py": "reference_test.py"}},
        bad={"kind": "happy-path tests only", "files": {f"tests/test_{module}.py": "weak_test.py"}},
    )


tasks["t01_elevation_tests"] = tests_task("elevation", "Write tests for elevation.py", [
    ("gain threshold exclusive", [e(EL, "if change > 0 and change >= threshold:", "if change > 0 and change > threshold:")]),
    ("no hysteresis", [e(EL, "            loss -= change\n            reference = elevation\n    return",
                             "            loss -= change\n            reference = elevation\n        reference = elevation\n    return")]),
    ("loss sign flipped", [e(EL, "            loss -= change\n", "            loss += change\n")]),
    ("default threshold 2 m", [e(EL, "DEFAULT_THRESHOLD_M = 3.0", "DEFAULT_THRESHOLD_M = 2.0")]),
    ("negative threshold clamped", [e(EL, '        raise ValueError("threshold must not be negative")', "        threshold = 0.0")]),
    ("steepest ignores descents", [e(EL, "abs(b.ele - a.ele) / (km * 1000) * 100", "(b.ele - a.ele) / (km * 1000) * 100")]),
    ("zero-length legs not skipped", [e(EL, "        if km == 0:\n            continue\n", "")]),
])
tasks["t02_pace_tests"] = tests_task("pace", "Write tests for pace.py", [
    ("flat speed 4 km/h", [e(PA, "FLAT_SPEED_KMH = 5.0", "FLAT_SPEED_KMH = 4.0")]),
    ("500 m per hour climb", [e(PA, "CLIMB_M_PER_HOUR = 600.0", "CLIMB_M_PER_HOUR = 500.0")]),
    ("fitness multiplies", [e(PA, "/ CLIMB_M_PER_HOUR) / fitness", "/ CLIMB_M_PER_HOUR) * fitness")]),
    ("zero fitness allowed", [e(PA, "if fitness <= 0:", "if fitness < 0:")]),
    ("negative ascent allowed", [e(PA, "if distance_km < 0 or ascent_m < 0:", "if distance_km < 0:")]),
    ("tobler peak on the wrong side", [e(PA, "abs(grade + 0.05)", "abs(grade - 0.05)")]),
    ("leg descent counted", [e(PA, "max(b.ele - a.ele, 0.0)", "abs(b.ele - a.ele)")]),
    ("leg fitness dropped", [e(PA, "naismith_hours(km, max(b.ele - a.ele, 0.0), fitness)", "naismith_hours(km, max(b.ele - a.ele, 0.0))")]),
])
tasks["t03_track_tests"] = tests_task("track", "Write tests for track.py", [
    ("feet not converted", [e(T, "return Point(lat, lon, ele * scale)", "return Point(lat, lon, ele)")]),
    ("blank lines not skipped", [e(T, "        if not line:\n            continue\n", "")]),
    ("range bounds exclusive", [e(T, "if not -90 <= lat <= 90 or not -180 <= lon <= 180:", "if not -90 < lat < 90 or not -180 < lon < 180:")]),
    ("one point accepted", [e(T, "if len(points) < 2:", "if len(points) < 1:")]),
    ("line numbers from 0", [e(T, "enumerate(text.splitlines(), start=1)", "enumerate(text.splitlines())")]),
    ("unknown units accepted", [e(T, 'if value not in ("m", "ft"):', "if not value:")]),
    ("default name empty", [e(T, 'name = default_name or "unnamed"', 'name = default_name or ""')]),
])

# ---------------------------------------------------------------- lint / types
NAISMITH_RETURN = "    return (distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR) / fitness\n"
tasks["l01_ruff"] = dict(
    tier="lint", title="Make ruff pass (an 'unused' variable is the fitness bug)",
    prompt=("`ruff check` reports problems in `src/`. Fix them so that `ruff check` passes, without "
            "changing the ruff configuration and without `noqa` comments."),
    setup=[
        e(T, "from trailhead.geo import haversine_km\n", "from trailhead.geo import haversine_km\nimport os\n"),
        e(T, "    except ValueError:\n        raise TrackError(f\"line {number}: not a number\") from None\n",
             "    except:\n        raise TrackError(f\"line {number}: not a number\")\n"),
        e(PA, NAISMITH_RETURN,
              "    hours = (distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR) / fitness\n"
              "    return distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR\n"),
        rm_test("tests/test_pace.py", "def test_fitness_scales_time():\n    assert naismith_hours(10, 600, fitness=1.5) == pytest.approx(2.0)\n\n\n"),
    ],
    grade={"kind": "lint", "checks": ["ruff"]},
    reference=RESTORE,
    bad={"kind": "deleted the unused variable", "restore_src": True, "edits": [
        e(PA, NAISMITH_RETURN, "    return distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR\n")]},
)
MYPY_PROMPT = ("`mypy` (strict mode, configured in `pyproject.toml`) reports errors in `src/`. Fix "
               "them so that `mypy` passes, without `# type: ignore`, `cast`, `Any`, or changes to "
               "the mypy configuration.")
tasks["l02_mypy_heading"] = dict(
    tier="lint", title="Make mypy pass (a None heading should be 'loop')",
    prompt=MYPY_PROMPT,
    setup=[
        e(G, "def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n",
             "def initial_bearing(lat1, lon1, lat2, lon2):\n"),
        e(RE, "def _heading(track: Track) -> str:\n", "def _heading(track: Track) -> str | None:\n"),
        e(RE, '        return "loop"\n', "        return None\n"),
    ],
    grade={"kind": "lint", "checks": ["mypy"]},
    reference=RESTORE,
    bad={"kind": "made the heading optional", "restore_src": True, "edits": [
        e(RE, "def _heading(track: Track) -> str:\n", "def _heading(track: Track) -> str | None:\n"),
        e(RE, '        return "loop"\n', "        return None\n"),
        e(RE, "    heading: str\n", "    heading: str | None\n"),
    ]},
)
tasks["l03_mypy_defaults"] = dict(
    tier="lint", title="Make mypy pass (two None defaults hide documented defaults)",
    prompt=MYPY_PROMPT,
    setup=[
        e(T, '    name = default_name or "unnamed"\n', "    name = default_name\n"),
        e(PL, "    track: Track, max_hours_per_day: float = DEFAULT_MAX_HOURS, fitness: float = 1.0\n",
              "    track: Track, max_hours_per_day: float | None = None, fitness: float = 1.0\n"),
        rm_test("tests/test_plan.py", "def test_everything_fits_in_one_day(five_flat_hours):\n"
                "    assert split_days(five_flat_hours) == [(1, 0, 5, 1.0 * 5)]\n\n\n"),
    ],
    grade={"kind": "lint", "checks": ["mypy"]},
    reference=RESTORE,
    bad={"kind": "empty-string name", "restore_src": True, "edits": [
        e(T, '    name = default_name or "unnamed"\n', '    name = default_name or ""\n')]},
)

# ---------------------------------------------------------------- one-file bugs (issue text)
tasks["b01_steady_climb"] = dict(
    tier="bug", title="A long climb in small steps shows no ascent",
    prompt=('Bug report from a user: "I recorded a long, steady climb with a point for every metre '
            "of height, about 300 m up in total. `trailhead summary` shows the ascent as +0 m. "
            'Tracks with bigger gaps between points look fine."' + FIX),
    setup=[
        e(EL, "            loss -= change\n            reference = elevation\n    return",
              "            loss -= change\n            reference = elevation\n        reference = elevation\n    return"),
        rm_test("tests/test_elevation.py", "def test_long_climb_in_small_steps_still_counts():\n"
                "    assert gain_and_loss([float(step) for step in range(1000, 1301)]) == (300.0, 0.0)\n\n\n"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "lowered the threshold to 1 m", "edits": [
        e(EL, "DEFAULT_THRESHOLD_M = 3.0", "DEFAULT_THRESHOLD_M = 1.0")]},
)
tasks["b02_heading_east"] = dict(
    tier="bug", title="A trail running due east is reported as heading N",
    prompt=('Bug report from a user: "`trailhead summary` says the heading is N for my ridge walk, '
            'which runs due east from 42.20, 23.30 to 42.20, 23.45."' + FIX),
    setup=[
        e(G, "    return (degrees(atan2(x, y)) + 360) % 360\n", "    return (degrees(atan2(y, x)) + 360) % 360\n"),
        rm_test("tests/test_geo.py", "@pytest.mark.parametrize(\n    (\"end\", \"expected\"),\n"
                "    [((1, 0), 0), ((0, 1), 90), ((-1, 0), 180), ((0, -1), 270)],\n)\n"
                "def test_bearing_along_the_axes(end, expected):\n"
                "    assert initial_bearing(0, 0, *end) == pytest.approx(expected)\n\n\n"),
        e("tests/test_geo.py", "from trailhead.geo import compass_point, haversine_km, initial_bearing\n",
          "from trailhead.geo import compass_point, haversine_km\n"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "rotated by 90 degrees", "edits": [
        e(G, "    return (degrees(atan2(y, x)) + 360) % 360\n", "    return (degrees(atan2(y, x)) + 90) % 360\n")]},
)
tasks["b03_day_overflow"] = dict(
    tier="bug", title="Day plans go over --max-hours",
    prompt=('Bug report from a user: "I ran `trailhead plan route.csv --max-hours 6` and day 1 came '
            "out at 6h 50m, even though no single stretch between two points takes more than an "
            'hour."' + FIX),
    setup=[
        e(PL, "        if used > 0 and used + hours > max_hours_per_day:\n",
              "        if used > 0 and used > max_hours_per_day:\n"),
        rm_test("tests/test_plan.py", "def test_days_respect_the_limit(five_flat_hours):\n"
                "    assert split_days(five_flat_hours, max_hours_per_day=2.5) == [\n"
                "        (1, 0, 2, 2.0),\n        (2, 2, 4, 2.0),\n        (3, 4, 5, 1.0),\n    ]\n\n\n"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "closes a day that exactly fills the limit", "edits": [
        e(PL, "        if used > 0 and used > max_hours_per_day:\n",
              "        if used > 0 and used + hours >= max_hours_per_day:\n")]},
)

# ---------------------------------------------------------------- two-file bugs (issue text)
tasks["h01_plan_fitness"] = dict(
    tier="two-file bug", title="plan ignores --fitness (cli.py and plan.py)",
    prompt=('Bug report from a user: "`trailhead plan route.csv --fitness 1.5` prints exactly the '
            "same days as `trailhead plan route.csv`. `trailhead summary` does take `--fitness` "
            'into account."' + FIX),
    setup=[
        e(PL, "leg_hours(track, fitness)", "leg_hours(track)"),
        e(CLI, "split_days(track, args.max_hours, args.fitness)", "split_days(track, args.max_hours)"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "fixed plan.py only", "edits": [e(PL, "leg_hours(track)", "leg_hours(track, fitness)")]},
)
tasks["h02_threshold_zero"] = dict(
    tier="two-file bug", title="--threshold 0 is ignored and --threshold 0.5 is rejected (report.py and cli.py)",
    prompt=('Bug report from a user: "`trailhead summary walk.csv --threshold 0` gives the same '
            "ascent as without the option, and `--threshold 0.5` is rejected with "
            "`invalid int value`. I want to count every change for a track I already smoothed.\""
            + FIX),
    setup=[
        e(RE, "    gain, loss = gain_and_loss([point.ele for point in track.points], threshold)\n",
              "    elevations = [point.ele for point in track.points]\n"
              "    gain, loss = gain_and_loss(elevations, threshold or DEFAULT_THRESHOLD_M)\n"),
        e(CLI, 'summary.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_M)',
               'summary.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD_M)'),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "fixed report.py only", "edits": [
        e(RE, "threshold or DEFAULT_THRESHOLD_M)", "threshold)")]},
)
tasks["h03_steepest_percent"] = dict(
    tier="two-file bug", title="steepest_grade returns a fraction; report.py compensates",
    prompt=('Bug report from a user: "`elevation.steepest_grade()` returns 0.18 for a track whose '
            "steepest stretch climbs 18 m over 100 m. The README and the docstring say it returns a "
            'percentage, so I expected 18.0."' + FIX),
    setup=[
        e(EL, "abs(b.ele - a.ele) / (km * 1000) * 100", "abs(b.ele - a.ele) / (km * 1000)"),
        e(EL, "    return round(steepest, 1)\n", "    return round(steepest, 3)\n"),
        e(RE, "steepest_pct=steepest_grade(track),", "steepest_pct=round(steepest_grade(track) * 100, 1),"),
        rm_test("tests/test_elevation.py", "\n\ndef test_steepest_grade_in_percent(make_track):\n"
                "    # 0.01 degrees of longitude on the equator is about 1112 m.\n"
                "    track = make_track((0, 0, 1000), (0, 0.01, 1100), (0, 0.02, 1050))\n"
                "    assert steepest_grade(track) == pytest.approx(9.0, abs=0.05)\n"),
        e("tests/test_elevation.py", "from trailhead.elevation import gain_and_loss, highest_and_lowest, steepest_grade\n",
          "from trailhead.elevation import gain_and_loss, highest_and_lowest\n"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "fixed elevation.py only", "edits": [
        e(EL, "abs(b.ele - a.ele) / (km * 1000)", "abs(b.ele - a.ele) / (km * 1000) * 100"),
        e(EL, "    return round(steepest, 3)\n", "    return round(steepest, 1)\n")]},
)

for name, spec in tasks.items():
    folder = TASKS / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "task.json").write_text(json.dumps({"id": name.split("_")[0], **spec}, indent=2) + "\n")
print(len(tasks), "tasks written")
