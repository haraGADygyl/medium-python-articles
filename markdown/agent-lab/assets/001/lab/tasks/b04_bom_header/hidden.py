from trailhead.cli import main
from trailhead.track import load_track

BOM = "﻿"


def test_bom_and_crlf_file(write_track):
    path = write_track(BOM + "lat,lon,ele\r\n0,0,1000\r\n0,0.01,1100\r\n", "export.csv")
    track = load_track(path)
    assert track.name == "export"
    assert [point.ele for point in track.points] == [1000, 1100]


def test_bom_before_a_comment_line(write_track):
    path = write_track(BOM + "# name: Ridge\r\n# units: ft\r\nlat,lon,ele\r\n0,0,1000\r\n0,0.01,2000\r\n")
    track = load_track(path)
    assert track.name == "Ridge"
    assert track.points[1].ele == 2000 * 0.3048


def test_summary_command_reads_a_bom_file(write_track, capsys):
    path = write_track(BOM + "lat,lon,ele\n0,0,1000\n0,0.01,1100\n", "garmin.csv")
    assert main(["summary", str(path)]) == 0
    assert capsys.readouterr().out.startswith("garmin\n")


def test_plain_files_still_work(write_track):
    assert load_track(write_track("lat,lon,ele\n0,0,1\n0,0.01,2\n")).points[0].ele == 1
