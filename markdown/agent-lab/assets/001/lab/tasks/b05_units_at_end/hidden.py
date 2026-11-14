import pytest

from trailhead.cli import main
from trailhead.track import parse_track

FT = 0.3048


@pytest.mark.parametrize(
    "text",
    [
        "# units: ft\nlat,lon,ele\n0,0,1000\n0,0.01,2000\n",
        "lat,lon,ele\n0,0,1000\n# units: ft\n0,0.01,2000\n",
        "lat,lon,ele\n0,0,1000\n0,0.01,2000\n# units: ft\n",
    ],
    ids=["before", "between", "after"],
)
def test_units_apply_to_every_point_wherever_they_appear(text):
    assert [p.ele for p in parse_track(text).points] == pytest.approx([1000 * FT, 2000 * FT])


def test_name_after_the_points_still_works():
    assert parse_track("lat,lon,ele\n0,0,1\n0,0.01,2\n# name: Late\n").name == "Late"


def test_metres_stay_metres():
    assert [p.ele for p in parse_track("lat,lon,ele\n0,0,1000\n0,0.01,2000\n# units: m\n").points] == [1000, 2000]


def test_pikes_peak_summary(write_track, capsys):
    path = write_track("# name: Pikes Peak\nlat,lon,ele\n38.8553,-104.9327,6700\n"
                       "38.8492,-104.9606,9800\n38.8405,-105.0442,14115\n# units: ft\n")
    assert main(["summary", str(path)]) == 0
    assert "  altitude  2042-4302 m\n" in capsys.readouterr().out
