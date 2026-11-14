from trailhead.cli import main

TRACK = "# name: Ridge\nlat,lon,ele\n0,0,1000\n0,0.01,1090\n0,0.02,1050\n"


def test_summary_command(write_track, capsys):
    assert main(["summary", str(write_track(TRACK))]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Ridge\n")
    assert "  distance  2.2 km\n" in out


def test_plan_command(write_track, capsys):
    assert main(["plan", str(write_track(TRACK)), "--max-hours", "0.3"]) == 0
    assert capsys.readouterr().out == "Day 1: points 0-1, 0h 22m\nDay 2: points 1-2, 0h 13m\n"


def test_missing_file_is_an_error(tmp_path, capsys):
    assert main(["summary", str(tmp_path / "nope.csv")]) == 1
    assert capsys.readouterr().err.startswith("trailhead: ")
