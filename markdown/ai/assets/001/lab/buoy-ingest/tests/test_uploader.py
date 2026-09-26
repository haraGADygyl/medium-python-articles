import pytest

from buoy_ingest.uploader import UploadFailed, Uploader, UploadTimeout


class FeedServer:
    """In-memory feed server. Applies each idempotency key once."""

    def __init__(self, timeouts=0, apply_before_timeout=False):
        self.timeouts = timeouts
        self.apply_before_timeout = apply_before_timeout
        self.applied: dict[str, int] = {}
        self.calls = 0

    def __call__(self, records, key):
        self.calls += 1
        if self.timeouts and self.apply_before_timeout:
            self.applied.setdefault(key, len(records))
        if self.timeouts:
            self.timeouts -= 1
            raise UploadTimeout()
        self.applied.setdefault(key, len(records))

    @property
    def records_applied(self):
        return sum(self.applied.values())


def test_send_first_time():
    server = FeedServer()
    receipt = Uploader(server).send([{"id": 1}, {"id": 2}])
    assert receipt.attempts == 1
    assert server.records_applied == 2


def test_send_retries_after_a_lost_request():
    server = FeedServer(timeouts=1)
    receipt = Uploader(server).send([{"id": 1}])
    assert receipt.attempts == 2
    assert server.records_applied == 1


def test_send_gives_up():
    server = FeedServer(timeouts=5)
    with pytest.raises(UploadFailed):
        Uploader(server, max_attempts=3).send([{"id": 1}])
    assert server.calls == 3
