from buoy_ingest.stats import summarise


def test_summary_is_the_documented_mean(make_observation):
    heights = [0.9, 1.1, 1.2, 1.4, 7.8]
    summary = summarise([make_observation(i, wave_height_m=h) for i, h in enumerate(heights)])
    assert summary["wave_height_m"] == 2.48


def test_mean_for_an_even_count(make_observation):
    heights = [1.0, 2.0, 3.0, 10.0]
    summary = summarise([make_observation(i, wave_height_m=h) for i, h in enumerate(heights)])
    assert summary["wave_height_m"] == 4.0
