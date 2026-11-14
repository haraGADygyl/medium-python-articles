import pytest

from trailhead.pace import naismith_hours


def test_naismith():
    assert naismith_hours(10, 600) == pytest.approx(3.0)


def test_negative_distance():
    with pytest.raises(ValueError):
        naismith_hours(-1, 0)
