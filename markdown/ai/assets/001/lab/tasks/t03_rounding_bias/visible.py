def test_summarise_does_not_round_before_averaging(make_observation):
    heights = [3.544, 3.544, 3.624]
    summary = summarise([make_observation(i, wave_height_m=h) for i, h in enumerate(heights)])
    assert summary["wave_height_m"] == 3.571
