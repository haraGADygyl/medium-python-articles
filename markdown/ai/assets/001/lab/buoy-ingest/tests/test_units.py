import pytest

from buoy_ingest.units import fahrenheit_to_celsius, knots_to_ms


def test_zero_knots_is_zero():
    assert knots_to_ms(0) == 0


def test_fahrenheit_freezing_point():
    assert fahrenheit_to_celsius(32) == pytest.approx(0.0)


def test_fahrenheit_body_temperature():
    assert fahrenheit_to_celsius(98.6) == pytest.approx(37.0)
