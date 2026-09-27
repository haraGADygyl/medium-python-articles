from buoy_ingest.uploader import Uploader, UploadTimeout


class KeyServer:
    def __init__(self, timeouts):
        self.timeouts = timeouts
        self.calls = []

    def __call__(self, records, key):
        self.calls.append((key, len(records)))
        if self.timeouts:
            self.timeouts -= 1
            raise UploadTimeout()


def test_each_chunk_has_its_own_key_kept_across_retries():
    server = KeyServer(timeouts=2)
    Uploader(server, max_attempts=3).send_chunked([{"id": i} for i in range(7)], chunk_size=3)
    keys = [key for key, _ in server.calls]
    assert keys[0] == keys[1] == keys[2]          # chunk 0 retried twice
    assert len(set(keys)) == 3                    # three chunks, three keys
    assert sum(n for _, n in server.calls[2:]) == 7


def test_chunk_keys_derive_from_one_batch_key():
    server = KeyServer(timeouts=0)
    Uploader(server, new_key=lambda: "batch42").send_chunked([{"id": i} for i in range(4)], chunk_size=2)
    assert all(key.startswith("batch42") for key, _ in server.calls)
    assert len({key for key, _ in server.calls}) == 2
