"""What CBOR's tags carry, next to the JSON workaround for the same value."""
import base64
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import cbor2

STAMP = datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc)
TRACE_ID = 0x9C3E1F0A6B2D48E7A15C0F93D4B8E261       # 128 bits
VOLTAGE = Decimal("13.10")
SIGNATURE = bytes(range(64))                        # an Ed25519-sized blob


def row(label: str, json_value: object, cbor_value: object,
        **options: object) -> None:
    """Encoded size of one value: the JSON workaround against CBOR."""
    as_json = json.dumps(json_value).encode()
    as_cbor = cbor2.dumps(cbor_value, **options)
    print(f"{label:<26}{len(as_json):>5} B json{len(as_cbor):>5} B cbor"
          f"   {as_cbor[:4].hex(' ')}")


def main() -> None:
    row("timestamp, tag 1", STAMP.isoformat(), STAMP,
        datetime_as_timestamp=True)
    row("timestamp, tag 0", STAMP.isoformat(), STAMP)
    row("128-bit id, tag 2", str(TRACE_ID), TRACE_ID)
    row("decimal 13.10, tag 4", str(VOLTAGE), VOLTAGE)
    row("64 raw bytes, type 2", base64.b64encode(SIGNATURE).decode(), SIGNATURE)
    row("NaN, half float", "NaN", float("nan"))

    print()
    print("what comes back")
    print(f"  tag 1:  {cbor2.loads(cbor2.dumps(STAMP, datetime_as_timestamp=True))!r}")
    print(f"  tag 2:  {cbor2.loads(cbor2.dumps(TRACE_ID)) == TRACE_ID}")
    print(f"  tag 4:  {cbor2.loads(cbor2.dumps(VOLTAGE))!r}")
    print(f"  json:   {json.loads(json.dumps(float(VOLTAGE)))!r}")

    offset = datetime(2026, 2, 11, 5, 15, tzinfo=timezone(timedelta(hours=1)))
    print()
    print("the offset survives tag 0 and not tag 1")
    print(f"  tag 0:  {cbor2.loads(cbor2.dumps(offset))}")
    print(f"  tag 1:  {cbor2.loads(cbor2.dumps(offset, datetime_as_timestamp=True))}")

    try:
        json.dumps(float("nan"), allow_nan=False)
    except ValueError as exc:
        print()
        print(f"strict json on NaN: ValueError: {exc}")


if __name__ == "__main__":
    main()
