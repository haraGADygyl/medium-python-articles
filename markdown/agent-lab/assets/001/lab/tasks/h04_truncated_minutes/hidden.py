from trailhead.cli import main
from trailhead.plan import describe_plan
from trailhead.report import format_summary, summarise

STEP = 3.74 / 111.19508  # 3.74 km of longitude on the equator


def test_summary_rounds_to_the_nearest_minute(make_track):
    text = format_summary(summarise(make_track((0, 0, 0), (0, STEP, 0))))
    assert "  time      0h 45m" in text


def test_summary_rounds_up_to_the_next_hour(make_track):
    track = make_track((0, 0, 0), (0, 9.999 / 111.19508, 0))  # 1.9998 h
    assert "  time      2h 00m" in format_summary(summarise(track))


def test_plan_rounds_to_the_nearest_minute():
    assert describe_plan([(1, 0, 5, 0.748), (2, 5, 9, 1.99)]) == [
        "Day 1: points 0-5, 0h 45m",
        "Day 2: points 5-9, 1h 59m",
    ]
    assert describe_plan([(1, 0, 3, 2.999)]) == ["Day 1: points 0-3, 3h 00m"]


def test_commands_round(write_track, capsys):
    path = str(write_track(f"lat,lon,ele\n0,0,0\n0,{STEP},0\n"))
    assert main(["summary", path]) == 0
    assert "  time      0h 45m\n" in capsys.readouterr().out
    assert main(["plan", path]) == 0
    assert capsys.readouterr().out == "Day 1: points 0-1, 0h 45m\n"
