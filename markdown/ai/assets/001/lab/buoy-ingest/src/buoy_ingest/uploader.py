"""Upload batches to the met office feed server, retrying on timeout."""
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass


class UploadTimeout(Exception):
    """The feed server did not acknowledge in time; it may or may not have applied the batch."""


class UploadFailed(Exception):
    """Every attempt timed out."""


@dataclass
class UploadReceipt:
    idempotency_key: str
    attempts: int


class Uploader:
    """Send batches to a feed client with bounded retries.

    `client(records, idempotency_key)` either returns normally or raises
    UploadTimeout. A retry must reuse the batch's idempotency key: the server
    may already have applied an attempt that timed out, and the key is how it
    recognises the resend.
    """

    def __init__(self, client: Callable[[Sequence[dict], str], None],
                 max_attempts: int = 3,
                 new_key: Callable[[], str] = lambda: uuid.uuid4().hex) -> None:
        self.client = client
        self.max_attempts = max_attempts
        self.new_key = new_key

    def send(self, records: Sequence[dict]) -> UploadReceipt:
        key = self.new_key()
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.client(records, key)
                return UploadReceipt(key, attempt)
            except UploadTimeout:
                continue
        raise UploadFailed(f"no acknowledgement after {self.max_attempts} attempts")
