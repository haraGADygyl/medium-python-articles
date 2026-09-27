def test_send_chunked_applies_every_record_once_after_a_timeout():
    server = FeedServer(timeouts=1, apply_before_timeout=True)
    Uploader(server).send_chunked([{"id": i} for i in range(5)], chunk_size=2)
    assert server.records_applied == 5
