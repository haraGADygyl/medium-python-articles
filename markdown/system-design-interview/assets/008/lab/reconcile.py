"""Compare what the provider charged with what the shop recorded."""
from common import provider_db, shop

INITIAL = 1_000_000 * 500


def reconcile() -> dict:
    with provider_db() as p:
        charges = dict(p.execute(
            "SELECT key, id FROM charge WHERE status = 'succeeded'").fetchall())
        slow = p.execute(
            "SELECT count(*), max(inbound_ms) FROM charge WHERE inbound_ms > 1000").fetchone()
        declined = p.execute(
            "SELECT count(*) FROM charge WHERE status = 'declined'").fetchone()[0]
    with shop() as s:
        orders = {k for (k,) in s.execute("SELECT checkout_key FROM orders")}
        states = dict(s.execute(
            "SELECT state, count(*) FROM checkout GROUP BY state").fetchall())
        failed = {k for (k,) in s.execute(
            "SELECT key FROM checkout WHERE state = 'failed'")}
        swept = dict(s.execute(
            "SELECT state, count(*) FROM checkout WHERE resolved_by = 'sweeper' "
            "GROUP BY state").fetchall())
        stock_out = INITIAL - s.execute(
            "SELECT sum(qty) FROM stock WHERE sku LIKE 'SKU-%'").fetchone()[0]
        pending = states.get("pending", 0)
        ages = s.execute(
            "SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY a)::numeric, 2), "
            "round(max(a)::numeric, 2) FROM (SELECT extract(epoch FROM resolved_at - created_at) a "
            "FROM checkout WHERE resolved_by = 'sweeper') t").fetchone()
    charged = set(charges)
    return {
        "charges succeeded": len(charges),
        "charges declined": declined,
        "orders": len(orders),
        "charged, no order": len(charged - orders),
        "  of those, checkout failed": len((charged - orders) & failed),
        "order, no charge": len(orders - charged),
        "checkouts pending": pending,
        "resolved by sweeper": swept,
        "sweeper resolve age p50/max s": f"{ages[0]} / {ages[1]}",
        "requests held > 1 s (max ms)": f"{slow[0]} ({slow[1]})",
        "stock out vs orders+pending": f"{stock_out} vs {len(orders) + pending}",
    }


if __name__ == "__main__":
    for k, v in reconcile().items():
        print(f"{k:<30}{v}")
