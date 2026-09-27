def test_summarise_reports_the_typical_wave(make_observation):
    heights = [0.9, 1.1, 1.2, 1.4, 7.8]   # one storm spike
    summary = summarise([make_observation(i, wave_height_m=h) for i, h in enumerate(heights)])
    assert summary["wave_height_m"] == 1.2
