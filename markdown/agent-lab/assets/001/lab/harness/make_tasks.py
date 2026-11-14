"""Writes tasks/*/task.json: the planted edits, prompts, grading specs and sample solutions.

The JSON files are what the harness reads; this script is how they were made, kept so a
task can be changed and regenerated. Hidden tests and reference files live beside each
task.json and are written by hand.

Fifteen tasks, three per tier: one easy baseline task (kept from calibration, where every
model passed it) and two harder ones per tier.

    python make_tasks.py && python verify.py
"""

import json
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "tasks"

G, T, EL, PA, PL, RE, CLI = ("src/trailhead/geo.py", "src/trailhead/track.py",
                             "src/trailhead/elevation.py", "src/trailhead/pace.py",
                             "src/trailhead/plan.py", "src/trailhead/report.py",
                             "src/trailhead/cli.py")
RESTORE = {"restore_src": True}
FIX = " Find the cause and fix it."


def e(file, old, new):
    return {"file": file, "old": old, "new": new}


def write(path, content):
    return {"write": path, "content": content}


def tests_task(module, mutants, baseline=False):
    return dict(
        tier="tests", baseline=baseline, title=f"Write tests for {module}.py",
        prompt=(f"`src/trailhead/{module}.py` has no tests. Write `tests/test_{module}.py` with "
                "pytest tests that check its behaviour as documented in the README and the "
                "docstrings. Don't change anything under `src/`."),
        setup=[{"delete": f"tests/test_{module}.py"}],
        grade={"kind": "mutants", "test_file": f"tests/test_{module}.py",
               "min_kills": len(mutants) - 1,
               "mutants": [{"name": name, "edits": edits} for name, edits in mutants]},
        reference={"files": {f"tests/test_{module}.py": "reference_test.py"}},
        bad={"kind": "happy-path tests only", "files": {f"tests/test_{module}.py": "weak_test.py"}},
    )


tasks = {}

# ====================================================================== refactor/feature
tasks["r01_rename_distance"] = dict(
    tier="refactor/feature", baseline=True,
    title="Rename haversine_km to distance_km with a deprecated alias",
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

LEGS_METHOD = '''    def leg_lengths_km(self) -> list[float]:
        """Length of each leg, the stretch between two consecutive points."""
        return [haversine_km(a.lat, a.lon, b.lat, b.lon) for a, b in pairwise(self.points)]
'''
tasks["r04_cache_legs"] = dict(
    tier="refactor/feature", baseline=False,
    title="Cache leg lengths on a mutable Track",
    prompt=("`Track.leg_lengths_km()` recomputes every great-circle distance each time it is "
            "called, and summarising a track calls it more than once. Cache the leg lengths so "
            "that a summary computes each leg's distance only once, without changing any results."),
    setup=[e("README.md", "- **Distance** is great-circle distance on a sphere of radius 6371.0088 km.\n",
             "- **Distance** is great-circle distance on a sphere of radius 6371.0088 km.\n"
             "- A `Track` is mutable: you can append to, replace or edit `track.points`, and its\n"
             "  lengths always reflect the current points.\n")],
    grade={"kind": "hidden"},
    reference={"edits": [
        e(T, "    points: list[Point] = field(default_factory=list)\n",
             "    points: list[Point] = field(default_factory=list)\n"
             "    _legs_key: tuple[Point, ...] | None = field(\n"
             "        default=None, init=False, repr=False, compare=False\n    )\n"
             "    _legs: list[float] = field(\n"
             "        default_factory=list, init=False, repr=False, compare=False\n    )\n"),
        e(T, LEGS_METHOD,
             '''    def leg_lengths_km(self) -> list[float]:
        """Length of each leg, the stretch between two consecutive points."""
        key = tuple(self.points)
        if key != self._legs_key:
            self._legs = [haversine_km(a.lat, a.lon, b.lat, b.lon) for a, b in pairwise(key)]
            self._legs_key = key
        return list(self._legs)
'''),
    ]},
    bad={"kind": "computed once, never invalidated", "edits": [
        e(T, "    points: list[Point] = field(default_factory=list)\n",
             "    points: list[Point] = field(default_factory=list)\n"
             "    _legs: list[float] | None = field(\n"
             "        default=None, init=False, repr=False, compare=False\n    )\n"),
        e(T, LEGS_METHOD,
             '''    def leg_lengths_km(self) -> list[float]:
        """Length of each leg, the stretch between two consecutive points."""
        if self._legs is None:
            self._legs = [haversine_km(a.lat, a.lon, b.lat, b.lon) for a, b in pairwise(self.points)]
        return list(self._legs)
'''),
    ]},
)

LEG_HOURS_GOLDEN_HEAD = '''def leg_hours(track: Track, fitness: float = 1.0) -> list[float]:
    """Naismith time for every leg.

    A leg's climb is the ascent the summary's rule credits to it
    (`elevation.counted_changes` with the default threshold), so the legs of a
    track add up to its summary time.
    """
'''
TOBLER_PACE = '''def tobler_leg_hours(track: Track, fitness: float = 1.0) -> list[float]:
    """Tobler time for every leg: length over Tobler speed at the leg's signed grade."""
    if fitness <= 0:
        raise ValueError("fitness must be positive")
    hours = []
    for (a, b), km in zip(pairwise(track.points), track.leg_lengths_km(), strict=True):
        if km == 0:
            hours.append(0.0)
            continue
        grade = (b.ele - a.ele) / (km * 1000)
        hours.append(km / tobler_kmh(grade) / fitness)
    return hours


def leg_hours(track: Track, fitness: float = 1.0, pace: str = "naismith") -> list[float]:
    """Walking time for every leg, by Naismith's rule (default) or Tobler's function.

    Under Naismith, a leg's climb is the ascent the summary's rule credits to it
    (`elevation.counted_changes` with the default threshold), so the legs of a
    track add up to its summary time.
    """
    if pace == "tobler":
        return tobler_leg_hours(track, fitness)
    if pace != "naismith":
        raise ValueError(f"unknown pace model {pace!r}")
'''


def tobler_edits(pace_code):
    return [
        e(PA, "from math import exp\n", "from itertools import pairwise\nfrom math import exp\n"),
        e(PA, LEG_HOURS_GOLDEN_HEAD, pace_code),
        e(PL, "    track: Track, max_hours_per_day: float = DEFAULT_MAX_HOURS, fitness: float = 1.0\n",
              "    track: Track,\n    max_hours_per_day: float = DEFAULT_MAX_HOURS,\n"
              "    fitness: float = 1.0,\n    pace: str = \"naismith\",\n"),
        e(PL, "leg_hours(track, fitness)", "leg_hours(track, fitness, pace)"),
        e(RE, "from trailhead.pace import naismith_hours\n",
              "from trailhead.pace import leg_hours, naismith_hours\n"),
        e(RE, "    track: Track, fitness: float = 1.0, threshold: float = DEFAULT_THRESHOLD_M\n",
              "    track: Track,\n    fitness: float = 1.0,\n"
              "    threshold: float = DEFAULT_THRESHOLD_M,\n    pace: str = \"naismith\",\n"),
        e(RE, "    length = track.length_km()\n",
              "    length = track.length_km()\n    if pace == \"naismith\":\n"
              "        hours = naismith_hours(length, gain, fitness)\n    else:\n"
              "        hours = sum(leg_hours(track, fitness, pace))\n"),
        e(RE, "        hours=naismith_hours(length, gain, fitness),\n", "        hours=hours,\n"),
        e(CLI, '    summary.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_M)\n',
               '    summary.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_M)\n'
               '    summary.add_argument("--pace", choices=["naismith", "tobler"], default="naismith")\n'),
        e(CLI, '    plan.add_argument("--fitness", type=float, default=1.0)\n',
               '    plan.add_argument("--fitness", type=float, default=1.0)\n'
               '    plan.add_argument("--pace", choices=["naismith", "tobler"], default="naismith")\n'),
        e(CLI, "summarise(track, args.fitness, args.threshold)",
               "summarise(track, args.fitness, args.threshold, args.pace)"),
        e(CLI, "split_days(track, args.max_hours, args.fitness)",
               "split_days(track, args.max_hours, args.fitness, args.pace)"),
    ]


tasks["r05_tobler_option"] = dict(
    tier="refactor/feature", baseline=False,
    title="Add Tobler as a pace model across pace, plan, report and the CLI",
    prompt=("Add Tobler's hiking function as an alternative to Naismith's rule for walking time. "
            "Give `pace.leg_hours`, `plan.split_days` and `report.summarise` a keyword argument "
            "`pace: str = \"naismith\"` that accepts `\"naismith\"` or `\"tobler\"` (anything else "
            "is a `ValueError`), and give both CLI commands a `--pace {naismith,tobler}` option. "
            "Under Tobler, a leg takes its length divided by `tobler_kmh(grade)` hours, where grade "
            "is the leg's elevation change divided by its horizontal length (both in metres); a "
            "zero-length leg takes no time; fitness divides the time as it does for Naismith; and "
            "the summary time is the sum of the leg times. Naismith stays the default and existing "
            "output must not change. Update the README."),
    setup=[], grade={"kind": "hidden"},
    reference={"edits": tobler_edits(TOBLER_PACE)},
    bad={"kind": "grade taken as an absolute value", "edits": tobler_edits(TOBLER_PACE.replace(
        "grade = (b.ele - a.ele) / (km * 1000)", "grade = abs(b.ele - a.ele) / (km * 1000)"))},
)

# ====================================================================== tests (mutation-graded)
tasks["t02_pace_tests"] = tests_task("pace", [
    ("flat speed 4 km/h", [e(PA, "FLAT_SPEED_KMH = 5.0", "FLAT_SPEED_KMH = 4.0")]),
    ("500 m per hour climb", [e(PA, "CLIMB_M_PER_HOUR = 600.0", "CLIMB_M_PER_HOUR = 500.0")]),
    ("fitness multiplies", [e(PA, "/ CLIMB_M_PER_HOUR) / fitness", "/ CLIMB_M_PER_HOUR) * fitness")]),
    ("zero fitness allowed", [e(PA, "if fitness <= 0:", "if fitness < 0:")]),
    ("negative ascent allowed", [e(PA, "if distance_km < 0 or ascent_m < 0:", "if distance_km < 0:")]),
    ("tobler peak on the wrong side", [e(PA, "abs(grade + 0.05)", "abs(grade - 0.05)")]),
    ("leg descent counted", [e(PA, "max(change, 0.0)", "abs(change)")]),
    ("leg fitness dropped", [e(PA, "naismith_hours(km, climb, fitness)", "naismith_hours(km, climb)")]),
], baseline=True)

tasks["t04_plan_tests"] = tests_task("plan", [
    ("a day that exactly fills the limit is closed early",
     [e(PL, "if used > 0 and used + hours > max_hours_per_day:",
            "if used > 0 and used + hours >= max_hours_per_day:")]),
    ("days numbered from 0",
     [e(PL, "days.append((len(days) + 1, first, index,", "days.append((len(days), first, index,"),
      e(PL, "days.append((len(days) + 1, first, len(track.points)",
            "days.append((len(days), first, len(track.points)")]),
    ("last day stops one point short",
     [e(PL, "len(track.points) - 1, round(used, 2)", "len(track.points) - 2, round(used, 2)")]),
    ("hours rounded to 0.1",
     [e(PL, "first, index, round(used, 2)))", "first, index, round(used, 1)))"),
      e(PL, "len(track.points) - 1, round(used, 2)))", "len(track.points) - 1, round(used, 1)))")]),
    ("zero limit allowed", [e(PL, "if max_hours_per_day <= 0:", "if max_hours_per_day < 0:")]),
    ("fitness dropped", [e(PL, "leg_hours(track, fitness)", "leg_hours(track)")]),
    ("minutes not zero-padded", [e(PL, "{whole}h {minutes:02d}m", "{whole}h {minutes}m")]),
    ("minutes truncated", [e(PL, "divmod(round(hours * 60), 60)", "divmod(int(hours * 60), 60)")]),
    ("next day starts one point late",
     [e(PL, "first, used = index, 0.0", "first, used = index + 1, 0.0")]),
])

tasks["t05_report_tests"] = tests_task("report", [
    ("loop radius 1 km", [e(RE, "LOOP_RADIUS_KM = 0.1", "LOOP_RADIUS_KM = 1.0")]),
    ("heading measured finish to start",
     [e(RE, "compass_point(initial_bearing(start.lat, start.lon, finish.lat, finish.lon))",
            "compass_point(initial_bearing(finish.lat, finish.lon, start.lat, start.lon))")]),
    ("distance rounded to 0.01", [e(RE, "length_km=round(length, 1),", "length_km=round(length, 2),")]),
    ("time uses descent", [e(RE, "hours=naismith_hours(length, gain, fitness),",
                             "hours=naismith_hours(length, loss, fitness),")]),
    ("fitness dropped", [e(RE, "hours=naismith_hours(length, gain, fitness),",
                           "hours=naismith_hours(length, gain),")]),
    ("threshold dropped", [e(RE, "gain_and_loss([point.ele for point in track.points], threshold)",
                             "gain_and_loss([point.ele for point in track.points])")]),
    ("altitude printed high-low", [e(RE, "{summary.lowest_m:.0f}-{summary.highest_m:.0f}",
                                     "{summary.highest_m:.0f}-{summary.lowest_m:.0f}")]),
    ("minutes truncated", [e(RE, "divmod(round(summary.hours * 60), 60)",
                             "divmod(int(summary.hours * 60), 60)")]),
    ("steepest rounded to whole percent", [e(RE, "steepest_pct=steepest_grade(track),",
                                             "steepest_pct=round(steepest_grade(track)),")]),
])

# ====================================================================== lint / types
NAISMITH_RETURN = "    return (distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR) / fitness\n"
tasks["l01_ruff"] = dict(
    tier="lint", baseline=True, title="Make ruff pass (an 'unused' variable is the fitness maths)",
    prompt=("`ruff check` reports problems in `src/`. Fix them so that `ruff check` passes, without "
            "changing the ruff configuration and without `noqa` comments."),
    setup=[
        e(T, "from trailhead.geo import haversine_km\n", "from trailhead.geo import haversine_km\nimport os\n"),
        e(T, "    except ValueError:\n        raise TrackError(f\"line {number}: not a number\") from None\n",
             "    except:\n        raise TrackError(f\"line {number}: not a number\")\n"),
        e(PA, NAISMITH_RETURN,
              "    hours = (distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR) / fitness\n"
              "    return distance_km / FLAT_SPEED_KMH + ascent_m / CLIMB_M_PER_HOUR\n"),
        e("tests/test_pace.py", "def test_fitness_scales_time():\n"
          "    assert naismith_hours(10, 600, fitness=1.5) == pytest.approx(2.0)\n\n\n", ""),
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
    tier="lint", baseline=False, title="Make mypy pass (a None heading should be 'loop')",
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

MISSING_ELE_TEST = '''def test_missing_elevation_is_none():
    track = parse_track("lat,lon,ele\\n0,0,100\\n0,0.01,\\n0,0.02,120\\n")
    assert [point.ele for point in track.points] == [100, None, 120]
    assert track.length_km() == pytest.approx(2.2239, abs=1e-3)


def test_default_name_comes_from_the_file(write_track):'''
tasks["l04_mypy_missing_elevation"] = dict(
    tier="lint", baseline=False,
    title="Make mypy pass after elevations became optional (`or 0.0` is the trap)",
    prompt=MYPY_PROMPT,
    setup=[
        e(T, "    ele: float  # metres\n", "    ele: float | None  # metres; None where the GPS lost it\n"),
        e(T, "        points = [Point(point.lat, point.lon, point.ele * scale) for point in points]\n",
             "        points = [\n            Point(p.lat, p.lon, None if p.ele is None else p.ele * scale)"
             " for p in points\n        ]\n"),
        e(T, "        lat, lon, ele = (float(part) for part in fields)\n",
             "        lat, lon = float(fields[0]), float(fields[1])\n"
             "        ele = float(fields[2]) if fields[2] else None\n"),
        e("README.md", "- Each point has three numbers. Latitude must be within -90 to 90 and longitude within\n"
          "  -180 to 180, both inclusive.\n",
          "- Each point has three numbers. Latitude must be within -90 to 90 and longitude within\n"
          "  -180 to 180, both inclusive.\n"
          "- The elevation may be left empty (`42.2031,23.3205,`) where the GPS lost it. Such a\n"
          "  point keeps `ele=None` and still counts for distance. Everywhere else (ascent and\n"
          "  descent, highest and lowest, steepest grade and walking time) it takes the elevation\n"
          "  of the nearest earlier point that has one or, if there is none, of the nearest later\n"
          "  point.\n"),
        e("tests/test_track.py", "def test_default_name_comes_from_the_file(write_track):", MISSING_ELE_TEST),
    ],
    grade={"kind": "lint", "checks": ["mypy"]},
    reference={"edits": [
        e(T, '''    def length_km(self) -> float:
        return sum(self.leg_lengths_km())
''', '''    def length_km(self) -> float:
        return sum(self.leg_lengths_km())

    def elevations(self) -> list[float]:
        """Every point's elevation, gaps filled from the nearest earlier point that has
        one, or the nearest later one when no earlier point has an elevation."""
        known = [point.ele for point in self.points if point.ele is not None]
        if not known:
            return [0.0] * len(self.points)
        filled: list[float] = []
        last = known[0]
        for point in self.points:
            if point.ele is not None:
                last = point.ele
            filled.append(last)
        return filled
'''),
        e(EL, "    elevations = [point.ele for point in track.points]\n",
              "    elevations = track.elevations()\n"),
        e(EL, "zip(pairwise(track.points), track.leg_lengths_km(), strict=True)",
              "zip(pairwise(track.elevations()), track.leg_lengths_km(), strict=True)"),
        e(EL, "abs(b.ele - a.ele) / (km * 1000) * 100", "abs(b - a) / (km * 1000) * 100"),
        e(PA, "counted_changes([p.ele for p in track.points])", "counted_changes(track.elevations())"),
        e(RE, "gain_and_loss([point.ele for point in track.points], threshold)",
              "gain_and_loss(track.elevations(), threshold)"),
    ]},
    bad={"kind": "missing elevations read as 0 m (`or 0.0`)", "edits": [
        e(EL, "    elevations = [point.ele for point in track.points]\n",
              "    elevations = [point.ele or 0.0 for point in track.points]\n"),
        e(EL, "abs(b.ele - a.ele) / (km * 1000) * 100",
              "abs((b.ele or 0.0) - (a.ele or 0.0)) / (km * 1000) * 100"),
        e(PA, "counted_changes([p.ele for p in track.points])",
              "counted_changes([p.ele or 0.0 for p in track.points])"),
        e(RE, "gain_and_loss([point.ele for point in track.points], threshold)",
              "gain_and_loss([point.ele or 0.0 for point in track.points], threshold)"),
    ]},
)

# ====================================================================== bugs (user reports)
tasks["b01_steady_climb"] = dict(
    tier="bug", baseline=True, title="A long climb in small steps shows no ascent",
    prompt=('Bug report from a user: "I recorded a long, steady climb with a point for every metre '
            "of height, about 300 m up in total. `trailhead summary` shows the ascent as +0 m. "
            'Tracks with bigger gaps between points look fine."' + FIX),
    setup=[
        e(EL, "        else:\n            changes.append(0.0)\n    return changes\n",
              "        else:\n            changes.append(0.0)\n        reference = elevation\n"
              "    return changes\n"),
        e("tests/test_elevation.py", "def test_long_climb_in_small_steps_still_counts():\n"
          "    assert gain_and_loss([float(step) for step in range(1000, 1301)]) == (300.0, 0.0)\n\n\n", ""),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "lowered the threshold to 1 m", "edits": [
        e(EL, "DEFAULT_THRESHOLD_M = 3.0", "DEFAULT_THRESHOLD_M = 1.0")]},
)

tasks["b04_bom_header"] = dict(
    tier="bug", baseline=False, title="Garmin exports fail on the header (a UTF-8 byte-order mark)",
    prompt=('Bug report from a user: "Track files exported from my Garmin app fail with '
            "`trailhead: line 1: expected the header 'lat,lon,ele'`, but when I open one in my "
            "editor the first line is exactly `lat,lon,ele`. One of the files is attached as "
            '`garmin-export.csv`."' + FIX),
    setup=[write("garmin-export.csv", "﻿lat,lon,ele\r\n42.2031,23.3205,2140\r\n"
                 "42.2049,23.3188,2196\r\n42.2060,23.3170,2250\r\n42.2071,23.3149,2281\r\n")],
    grade={"kind": "hidden"},
    reference={"edits": [e(T, 'path.read_text(encoding="utf-8")', 'path.read_text(encoding="utf-8-sig")')]},
    bad={"kind": "strips the mark only when comparing the header", "edits": [
        e(T, 'if [column.strip() for column in line.split(",")] != HEADER:',
             'if [column.strip() for column in line.lstrip("\\ufeff").split(",")] != HEADER:')]},
)

tasks["b05_units_at_end"] = dict(
    tier="bug", baseline=False, title="A `# units: ft` line after the points is ignored",
    prompt=('Bug report from a user: "My GPS app writes the `# units: ft` line at the end of the '
            "file, after the points. trailhead then reports a highest point of 14115 m for a hike "
            "that tops out at 14,115 ft (about 4302 m). The file is attached as `pikes-peak.csv`.\""
            + FIX),
    setup=[
        e(T, "        points.append(_parse_point(line, number))\n",
             "        points.append(_parse_point(line, number, scale))\n"),
        e(T, "    if scale != 1.0:\n"
             "        points = [Point(point.lat, point.lon, point.ele * scale) for point in points]\n", ""),
        e(T, "def _parse_point(line: str, number: int) -> Point:",
             "def _parse_point(line: str, number: int, scale: float) -> Point:"),
        e(T, "    return Point(lat, lon, ele)\n", "    return Point(lat, lon, ele * scale)\n"),
        write("pikes-peak.csv", "# name: Pikes Peak via Barr Trail\nlat,lon,ele\n38.8553,-104.9327,6700\n"
              "38.8492,-104.9606,9800\n38.8405,-105.0442,14115\n# units: ft\n"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "scales again after parsing (double-scales a leading units line)", "edits": [
        e(T, "    return Track(name, points)\n",
             "    if scale != 1.0:\n        points = [Point(p.lat, p.lon, p.ele * scale) for p in points]\n"
             "    return Track(name, points)\n")]},
)

# ====================================================================== two-file bugs (user reports)
tasks["h03_steepest_percent"] = dict(
    tier="two-file bug", baseline=True, title="steepest_grade returns a fraction; report.py compensates",
    prompt=('Bug report from a user: "`elevation.steepest_grade()` returns 0.18 for a track whose '
            "steepest stretch climbs 18 m over 100 m. The README and the docstring say it returns a "
            'percentage, so I expected 18.0."' + FIX),
    setup=[
        e(EL, "abs(b.ele - a.ele) / (km * 1000) * 100", "abs(b.ele - a.ele) / (km * 1000)"),
        e(EL, "    return round(steepest, 1)\n", "    return round(steepest, 3)\n"),
        e(RE, "steepest_pct=steepest_grade(track),", "steepest_pct=round(steepest_grade(track) * 100, 1),"),
        e("tests/test_elevation.py", "\n\ndef test_steepest_grade_in_percent(make_track):\n"
          "    # 0.01 degrees of longitude on the equator is about 1112 m.\n"
          "    track = make_track((0, 0, 1000), (0, 0.01, 1100), (0, 0.02, 1050))\n"
          "    assert steepest_grade(track) == pytest.approx(9.0, abs=0.05)\n", ""),
        e("tests/test_elevation.py",
          "from trailhead.elevation import gain_and_loss, highest_and_lowest, steepest_grade\n",
          "from trailhead.elevation import gain_and_loss, highest_and_lowest\n"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "fixed elevation.py only", "edits": [
        e(EL, "abs(b.ele - a.ele) / (km * 1000)", "abs(b.ele - a.ele) / (km * 1000) * 100"),
        e(EL, "    return round(steepest, 3)\n", "    return round(steepest, 1)\n")]},
)

tasks["h04_truncated_minutes"] = dict(
    tier="two-file bug", baseline=False,
    title="Durations truncated, not rounded (the same copied code in report.py and plan.py)",
    prompt=('Bug report from a user: "`trailhead summary` shows `time 0h 44m` for a flat 3.74 km '
            "walk. By Naismith's rule that is 44.9 minutes, and the README says times are rounded "
            'to the nearest minute."' + FIX),
    setup=[
        e(PL, "divmod(round(hours * 60), 60)", "divmod(int(hours * 60), 60)"),
        e(RE, "divmod(round(summary.hours * 60), 60)", "divmod(int(summary.hours * 60), 60)"),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "fixed report.py only", "edits": [
        e(RE, "divmod(int(summary.hours * 60), 60)", "divmod(round(summary.hours * 60), 60)")]},
)

tasks["h05_plan_matches_summary"] = dict(
    tier="two-file bug", baseline=False,
    title="Plan days don't add up to the summary on noisy tracks (pace.py ignores the ascent rule)",
    prompt=('Bug report from a user: "On my GPS track, which has a lot of small up-and-down noise, '
            "the days from `trailhead plan` add up to 9h 40m, but `trailhead summary` says 7h 05m "
            'for the same file. The README says the two should agree."' + FIX),
    setup=[
        e(PA, "from math import exp\n\nfrom trailhead.elevation import counted_changes\n"
              "from trailhead.track import Track\n",
              "from itertools import pairwise\nfrom math import exp\n\nfrom trailhead.track import Track\n"),
        e(PA, LEG_HOURS_GOLDEN_HEAD + '''    climbs = [max(change, 0.0) for change in counted_changes([p.ele for p in track.points])]
    return [
        naismith_hours(km, climb, fitness)
        for km, climb in zip(track.leg_lengths_km(), climbs, strict=True)
    ]
''', '''def leg_hours(track: Track, fitness: float = 1.0) -> list[float]:
    """Naismith time for every leg, counting the leg's own climb."""
    return [
        naismith_hours(km, max(b.ele - a.ele, 0.0), fitness)
        for (a, b), km in zip(pairwise(track.points), track.leg_lengths_km(), strict=True)
    ]
'''),
    ],
    grade={"kind": "hidden"}, reference=RESTORE,
    bad={"kind": "threshold applied to each leg on its own", "edits": [
        e(PA, "naismith_hours(km, max(b.ele - a.ele, 0.0), fitness)",
              "naismith_hours(km, b.ele - a.ele if b.ele - a.ele >= 3 else 0.0, fitness)")]},
)

for name, spec in tasks.items():
    folder = TASKS / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "task.json").write_text(json.dumps({"id": name.split("_")[0], **spec}, indent=2,
                                                 ensure_ascii=False) + "\n")
print(len(tasks), "tasks written")
