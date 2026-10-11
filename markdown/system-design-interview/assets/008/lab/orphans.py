"""After a storm: how long did each orphaned charge spend in flight?"""
from common import provider_db, shop

with shop() as s:
    orders = {k for (k,) in s.execute("SELECT checkout_key FROM orders")}
with provider_db() as p:
    rows = p.execute("SELECT key, inbound_ms FROM charge "
                     "WHERE status = 'succeeded'").fetchall()
inflight = sorted(ms for key, ms in rows if key not in orders)
print(f"orphaned charges: {len(inflight)}")
if inflight:
    print(f"time in flight before the provider recorded them: "
          f"min {inflight[0]} ms, max {inflight[-1]} ms")
