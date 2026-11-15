import pytest

from trailhead.geo import initial_bearing
from trailhead.report import format_summary, summarise

LOOP = ((0, 0, 1000), (0, 0.01, 1100), (0.0005, 0.0003, 1000))


def test_loop_heading_is_loop(make_track):
    # The README says the summary shows `loop`; the printed summary is what counts.
    # The Summary field may hold "loop" or None (grader v2, after reading the transcripts).
    summary = summarise(make_track(*LOOP, name="Lake Circuit"))
    assert summary.heading in ("loop", None)
    assert format_summary(summary).endswith("\n  heading   loop")


def test_bearing_unchanged():
    assert initial_bearing(0, 0, 0, 1) == pytest.approx(90)
    assert initial_bearing(0, 0, -1, 0) == pytest.approx(180)


def test_non_loop_heading(make_track):
    assert summarise(make_track((0, 0, 0), (0, 0.01, 0), (0, 0.03, 0))).heading == "E"
