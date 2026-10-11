"""A fake payment provider: its own process, its own database.

POST /charges is idempotent on `key`. Every request spends 40-60 ms in
flight before the provider records anything, and 40-60 ms after. A fraction
TAIL_P of requests are held TAIL_MIN..TAIL_MAX seconds before they arrive:
a slow network path, a retrying load balancer, a provider queue.
"""
import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from common import provider_db

TAIL_P = float(os.environ.get("TAIL_P", "0"))
TAIL_MIN = float(os.environ.get("TAIL_MIN", "1"))
TAIL_MAX = float(os.environ.get("TAIL_MAX", "8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the caller died; the charge stands anyway

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        inbound = random.uniform(0.04, 0.06)
        if random.random() < TAIL_P:
            inbound = random.uniform(TAIL_MIN, TAIL_MAX)
        time.sleep(inbound)                       # in flight, nothing recorded
        status = "declined" if req["card"] == "card_declined" else "succeeded"
        with provider_db() as conn:
            row = conn.execute(
                "INSERT INTO charge (key, amount, status, inbound_ms) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (key) DO NOTHING RETURNING id, status",
                (req["key"], req["amount"], status, round(inbound * 1000))).fetchone()
            if row is None:                       # same key seen before
                row = conn.execute("SELECT id, status FROM charge WHERE key = %s",
                                   (req["key"],)).fetchone()
        time.sleep(random.uniform(0.04, 0.06))    # response on its way back
        self.reply(200, {"id": row[0], "status": row[1]})

    def do_GET(self):
        key = parse_qs(urlparse(self.path).query)["key"][0]
        with provider_db() as conn:
            row = conn.execute("SELECT id, status FROM charge WHERE key = %s",
                               (key,)).fetchone()
        time.sleep(random.uniform(0.04, 0.06))
        if row is None:
            self.reply(404, {"error": "no such charge"})
        else:
            self.reply(200, {"id": row[0], "status": row[1]})


if __name__ == "__main__":
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 256
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8099"))),
                        Handler).serve_forever()
