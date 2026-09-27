def test_every_attempt_uses_a_fresh_key():
    server = FeedServer(timeouts=1, apply_before_timeout=True)
    Uploader(server).send([{"id": 1}])
    assert len(server.applied) == 2
