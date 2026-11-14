from trailhead.elevation import gain_and_loss, highest_and_lowest


def test_gain_and_loss():
    assert gain_and_loss([100, 150, 120]) == (50.0, 30.0)


def test_highest_and_lowest(make_track):
    assert highest_and_lowest(make_track((0, 0, 900), (0, 0.01, 1450))) == (1450, 900)
