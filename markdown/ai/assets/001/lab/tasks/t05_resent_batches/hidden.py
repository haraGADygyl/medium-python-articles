from buoy_ingest.ingest import merge_batches


def test_the_first_copy_wins(make_observation):
    first = [make_observation(5, wave_height_m=1.0)]
    resent = [make_observation(5, wave_height_m=9.9)]
    [kept] = merge_batches([first, resent])
    assert kept.wave_height_m == 1.0


def test_duplicates_inside_one_batch_and_across_three(make_observation):
    batches = [[make_observation(8), make_observation(8)],
               [make_observation(9)], [make_observation(8), make_observation(9), make_observation(10)]]
    assert [o.observation_id for o in merge_batches(batches)] == [8, 9, 10]
