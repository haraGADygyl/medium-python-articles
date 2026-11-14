from trailhead.report import format_summary, summarise


def test_summary_has_a_name(make_track):
    summary = summarise(make_track((0, 0, 0), (0, 0.01, 0), name="Flat"))
    assert format_summary(summary).startswith("Flat\n")
