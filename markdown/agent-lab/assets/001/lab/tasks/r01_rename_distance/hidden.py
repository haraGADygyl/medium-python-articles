import warnings
from pathlib import Path

import pytest

import trailhead
from trailhead import geo

PACKAGE = Path(trailhead.__file__).parent


def test_distance_km_is_the_new_name():
    assert geo.distance_km(0, 0, 0, 0.01) == pytest.approx(1.11195, abs=1e-4)


def test_old_name_warns_and_returns_the_same_value():
    with pytest.warns(DeprecationWarning):
        value = geo.haversine_km(42.1, 23.3, 42.2, 23.4)
    assert value == pytest.approx(geo.distance_km(42.1, 23.3, 42.2, 23.4))


def test_new_name_does_not_warn():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        geo.distance_km(1, 2, 3, 4)


def test_no_other_module_uses_the_old_name():
    for path in PACKAGE.glob("*.py"):
        if path.name != "geo.py":
            assert "haversine_km" not in path.read_text(), path.name


def test_package_code_does_not_trigger_the_warning(make_track):
    from trailhead.report import summarise

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        summarise(make_track((0, 0, 0), (0, 0.01, 10), (0, 0.02, 0)))
