from math import exp

import pytest

from trailhead.cli import main
from trailhead.geo import haversine_km
from trailhead.pace import leg_hours
from trailhead.plan import split_days
from trailhead.report import format_summary, summarise

# Up 100 m, a repeated point, down 150 m, then flat.
POINTS = ((0, 0, 1000), (0, 0.01, 1100), (0, 0.01, 1100), (0, 0.02, 950), (0, 0.03, 950))


def tobler(points, fitness=1.0):
    hours = []
    for a, b in zip(points, points[1:]):
        km = haversine_km(a[0], a[1], b[0], b[1])
        if km == 0:
            hours.append(0.0)
            continue
        grade = (b[2] - a[2]) / (km * 1000)
        hours.append(km / (6 * exp(-3.5 * abs(grade + 0.05))) / fitness)
    return hours


def test_tobler_leg_hours(make_track):
    got = leg_hours(make_track(*POINTS), pace="tobler")
    assert got == pytest.approx(tobler(POINTS), rel=1e-6)
    assert got[1] == 0.0


def test_tobler_downhill_is_not_the_same_as_uphill(make_track):
    got = leg_hours(make_track(*POINTS), pace="tobler")
    assert got[0] != pytest.approx(got[2], rel=1e-3)


def test_fitness_divides_tobler_time(make_track):
    got = leg_hours(make_track(*POINTS), fitness=1.25, pace="tobler")
    assert got == pytest.approx(tobler(POINTS, 1.25), rel=1e-6)


def test_default_is_still_naismith(make_track):
    track = make_track(*POINTS)
    assert leg_hours(track) == pytest.approx(leg_hours(track, pace="naismith"))
    assert summarise(track).hours == pytest.approx(summarise(track, pace="naismith").hours)


def test_summary_time_is_the_sum_of_tobler_legs(make_track):
    summary = summarise(make_track(*POINTS), pace="tobler")
    assert summary.hours == pytest.approx(sum(tobler(POINTS)), rel=1e-6)


def test_split_days_with_tobler(make_track):
    days = split_days(make_track(*POINTS), max_hours_per_day=0.3, pace="tobler")
    assert sum(day[3] for day in days) == pytest.approx(sum(tobler(POINTS)), abs=0.02)
    assert days[-1][2] == len(POINTS) - 1


@pytest.mark.parametrize("call", ["legs", "plan", "summary"])
def test_unknown_pace_is_a_value_error(make_track, call):
    track = make_track(*POINTS)
    with pytest.raises(ValueError):
        if call == "legs":
            leg_hours(track, pace="scarf")
        elif call == "plan":
            split_days(track, pace="scarf")
        else:
            summarise(track, pace="scarf")


def test_cli_pace_option(write_track, capsys, make_track):
    text = "lat,lon,ele\n" + "".join(f"{a},{b},{c}\n" for a, b, c in POINTS)
    path = str(write_track(text))
    assert main(["summary", path, "--pace", "tobler"]) == 0
    expected = format_summary(summarise(make_track(*POINTS, name="walk"), pace="tobler"))
    assert capsys.readouterr().out == expected + "\n"
    assert main(["plan", path, "--pace", "tobler", "--max-hours", "0.3"]) == 0
    tobler_plan = capsys.readouterr().out
    assert main(["plan", path, "--max-hours", "0.3"]) == 0
    assert capsys.readouterr().out != tobler_plan
