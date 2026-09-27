from buoy_ingest.uploader import Uploader, UploadTimeout


class RecordingServer:
    def __init__(self, timeouts):
        self.timeouts = timeouts
        self.keys = []

    def __call__(self, records, key):
        self.keys.append(key)
        if self.timeouts:
            self.timeouts -= 1
            raise UploadTimeout()


def test_every_attempt_carries_the_same_key():
    server = RecordingServer(timeouts=2)
    receipt = Uploader(server, max_attempts=3).send([{"id": 1}])
    assert len(server.keys) == 3
    assert len(set(server.keys)) == 1
    assert receipt.idempotency_key == server.keys[0]


def test_each_batch_gets_its_own_key():
    server = RecordingServer(timeouts=0)
    uploader = Uploader(server)
    uploader.send([{"id": 1}])
    uploader.send([{"id": 2}])
    assert server.keys[0] != server.keys[1]
