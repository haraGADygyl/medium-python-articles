import pytest

from buoy_ingest.units import MS_PER_KNOT, knots_to_ms


def test_conversion_factor():
    assert MS_PER_KNOT == pytest.approx(0.514444, abs=1e-6)


def test_storm_force_gust():
    assert knots_to_ms(55) == pytest.approx(28.29442, abs=1e-4)
