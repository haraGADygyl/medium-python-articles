import pytest

from trailhead.pace import leg_hours, naismith_hours, tobler_kmh


def test_flat_is_five_km_per_hour():
    assert naismith_hours(10, 0) == pytest.approx(2.0)


def test_six_hundred_metres_adds_an_hour():
    assert naismith_hours(0, 600) == pytest.approx(1.0)


def test_fitness_divides_time():
    assert naismith_hours(10, 600, fitness=1.5) == pytest.approx(2.0)


@pytest.mark.parametrize(("km", "ascent", "fitness"), [(-1, 0, 1), (1, -5, 1), (1, 0, 0), (1, 0, -1)])
def test_invalid_arguments(km, ascent, fitness):
    with pytest.raises(ValueError):
        naismith_hours(km, ascent, fitness)


def test_tobler():
    assert tobler_kmh(-0.05) == pytest.approx(6.0)
    assert tobler_kmh(0.1) < tobler_kmh(-0.1)


def test_leg_hours_ignore_descent_and_use_fitness(make_track):
    track = make_track((0, 0, 1000), (0, 0.01, 1300), (0, 0.02, 1000))
    climb, descent = leg_hours(track)
    assert climb == pytest.approx(1.11195 / 5 + 0.5, abs=1e-4)
    assert descent == pytest.approx(1.11195 / 5, abs=1e-4)
    assert leg_hours(track, fitness=2) == pytest.approx([climb / 2, descent / 2])
