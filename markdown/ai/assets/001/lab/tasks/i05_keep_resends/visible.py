def test_merge_batches_keeps_every_copy_for_audit(make_observation):
    first = [make_observation(1), make_observation(2)]
    resent = [make_observation(2), make_observation(3)]
    assert [o.observation_id for o in merge_batches([first, resent])] == [1, 2, 2, 3]
