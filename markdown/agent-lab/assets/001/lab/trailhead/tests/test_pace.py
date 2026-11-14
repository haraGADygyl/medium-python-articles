import pytest

from trailhead.pace import leg_hours, naismith_hours, tobler_kmh


def test_naismith_on_the_flat_and_uphill():
    assert naismith_hours(10, 0) == pytest.approx(2.0)
    assert naismith_hours(10, 600) == pytest.approx(3.0)


def test_fitness_scales_time():
    assert naismith_hours(10, 600, fitness=1.5) == pytest.approx(2.0)


@pytest.mark.parametrize(("km", "ascent", "fitness"), [(-1, 0, 1), (1, -5, 1), (1, 0, 0)])
def test_invalid_arguments(km, ascent, fitness):
    with pytest.raises(ValueError):
        naismith_hours(km, ascent, fitness)


def test_tobler_peaks_on_a_gentle_descent():
    assert tobler_kmh(-0.05) == pytest.approx(6.0)
    assert tobler_kmh(0.0) == pytest.approx(5.036, abs=1e-3)


def test_leg_hours(make_track):
    track = make_track((0, 0, 1000), (0, 0.01, 1300), (0, 0.02, 1000))
    climb, descent = leg_hours(track)
    assert climb == pytest.approx(1.11195 / 5 + 0.5, abs=1e-4)
    assert descent == pytest.approx(1.11195 / 5, abs=1e-4)
