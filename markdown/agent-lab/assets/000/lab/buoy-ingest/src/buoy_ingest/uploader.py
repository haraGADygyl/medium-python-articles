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

    def send_chunked(self, records: Sequence[dict], chunk_size: int) -> list[UploadReceipt]:
        """Send a large batch in chunks the feed server accepts.

        Each chunk carries its own idempotency key, derived from one batch key
        and the chunk's position, so every chunk is applied exactly once and a
        retried chunk reuses its key.
        """
        batch_key = self.new_key()
        receipts = []
        for index, start in enumerate(range(0, len(records), chunk_size)):
            chunk = records[start:start + chunk_size]
            chunk_key = f"{batch_key}-{index}"
            receipts.append(self._send_with_key(chunk, chunk_key))
        return receipts

    def _send_with_key(self, records: Sequence[dict], key: str) -> UploadReceipt:
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.client(records, key)
                return UploadReceipt(key, attempt)
            except UploadTimeout:
                continue
        raise UploadFailed(f"no acknowledgement after {self.max_attempts} attempts")
