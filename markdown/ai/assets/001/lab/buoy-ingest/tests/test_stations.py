import pytest

from buoy_ingest.stations import lookup, station_for


def test_lookup_exact_name():
    assert lookup("Aberdeen Approach") == ("Aberdeen Approach", ("NE-07", "NE-08"))


def test_lookup_ignores_case_and_spaces():
    assert lookup("  stonehaven BAY ")[0] == "Stonehaven Bay"


def test_lookup_unknown_station():
    with pytest.raises(KeyError):
        lookup("Lerwick")


def test_station_for_buoy():
    assert station_for("HB-301") == "Tórshavn Outer"
    assert station_for("XX-00") is None
