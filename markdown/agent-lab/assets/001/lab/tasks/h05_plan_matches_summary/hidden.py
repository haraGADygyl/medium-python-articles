import pytest

from trailhead.cli import main
from trailhead.pace import leg_hours
from trailhead.plan import split_days
from trailhead.report import summarise

STEP = 0.002  # about 222 m of longitude per leg on the equator
JITTER = [1000, 1001.5, 999.5, 1001, 1002, 1000, 1001.5, 999, 1000.5, 1002, 1000] * 4
CLIMB = [1000 + i for i in range(301)]  # 300 m in 1 m steps


def track(make_track, elevations):
    return make_track(*[(0, i * STEP, ele) for i, ele in enumerate(elevations)])


def test_plan_days_add_up_to_the_summary_on_a_noisy_track(make_track):
    noisy = track(make_track, JITTER)
    total = sum(day[3] for day in split_days(noisy, max_hours_per_day=0.5))
    assert total == pytest.approx(summarise(noisy).hours, abs=0.03)


def test_jitter_adds_no_climbing_time(make_track):
    noisy = track(make_track, JITTER)
    assert sum(leg_hours(noisy)) == pytest.approx(noisy.length_km() / 5, rel=1e-6)


def test_a_climb_in_small_steps_still_costs_its_time(make_track):
    climb = track(make_track, CLIMB)
    assert sum(leg_hours(climb)) == pytest.approx(climb.length_km() / 5 + 300 / 600, rel=1e-4)


def test_fitness_keeps_them_in_step(make_track):
    noisy = track(make_track, JITTER)
    total = sum(day[3] for day in split_days(noisy, max_hours_per_day=0.5, fitness=1.4))
    assert total == pytest.approx(summarise(noisy, fitness=1.4).hours, abs=0.03)


def test_commands_agree(write_track, capsys):
    text = "lat,lon,ele\n" + "".join(f"0,{i * STEP},{ele}\n" for i, ele in enumerate(JITTER))
    path = str(write_track(text))
    assert main(["summary", path]) == 0
    summary_time = [line for line in capsys.readouterr().out.splitlines() if "time" in line][0]
    assert main(["plan", path, "--max-hours", "20"]) == 0
    assert capsys.readouterr().out.rstrip().endswith(summary_time.split()[-2] + " " + summary_time.split()[-1])
