def test_retry_after_an_applied_timeout_is_applied_once():
    server = FeedServer(timeouts=1, apply_before_timeout=True)
    Uploader(server).send([{"id": 1}, {"id": 2}])
    assert server.records_applied == 2
