from trailhead.plan import describe_plan, split_days


def test_split_days_returns_days(make_track):
    track = make_track((0, 0, 0), (0, 0.01, 0), (0, 0.02, 0))
    assert len(split_days(track)) == 1


def test_describe_plan():
    assert describe_plan([(1, 0, 2, 1.5)]) == ["Day 1: points 0-2, 1h 30m"]
