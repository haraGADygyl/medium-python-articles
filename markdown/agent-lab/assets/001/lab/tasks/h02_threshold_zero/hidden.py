from trailhead.cli import main
from trailhead.report import summarise

TRACK = "lat,lon,ele\n0,0,1000\n0,0.001,1001\n0,0.002,1000.5\n0,0.003,1002\n0,0.004,1001\n"


def test_zero_threshold_counts_every_change(make_track):
    track = make_track((0, 0, 1000), (0, 0.001, 1001), (0, 0.002, 1000.5), (0, 0.003, 1002))
    summary = summarise(track, threshold=0)
    assert (summary.gain_m, summary.loss_m) == (2.5, 0.5)
    assert (summarise(track).gain_m, summarise(track).loss_m) == (0.0, 0.0)


def test_cli_threshold_zero(write_track, capsys):
    assert main(["summary", str(write_track(TRACK)), "--threshold", "0"]) == 0
    assert "  ascent    +2 m / -2 m\n" in capsys.readouterr().out


def test_cli_fractional_threshold(write_track, capsys):
    assert main(["summary", str(write_track(TRACK)), "--threshold", "0.75"]) == 0
    assert "  ascent    +2 m / -1 m\n" in capsys.readouterr().out


def test_cli_default_threshold(write_track, capsys):
    assert main(["summary", str(write_track(TRACK))]) == 0
    assert "  ascent    +0 m / -0 m\n" in capsys.readouterr().out
