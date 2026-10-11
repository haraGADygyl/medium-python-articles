"""Shared helpers: connections and the HTTP calls to the provider."""
import json
import os
import urllib.error
import urllib.request

import psycopg

DSN = os.environ.get("DSN", "host=localhost port=55438 user=postgres password=lab")
PROVIDER = os.environ.get("PROVIDER", "http://127.0.0.1:8099")


def shop() -> psycopg.Connection:
    return psycopg.connect(f"{DSN} dbname=shop", autocommit=True)


def provider_db() -> psycopg.Connection:
    return psycopg.connect(f"{DSN} dbname=provider", autocommit=True)


def charge(key: str, amount: int, card: str, timeout: float = 30.0) -> dict:
    """POST /charges with an idempotency key. Same key, same charge."""
    body = json.dumps({"key": key, "amount": amount, "card": card}).encode()
    req = urllib.request.Request(f"{PROVIDER}/charges", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def lookup(key: str) -> dict | None:
    """GET /charges?key=... -> the charge, or None if the provider has none."""
    try:
        with urllib.request.urlopen(f"{PROVIDER}/charges?key={key}", timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise
