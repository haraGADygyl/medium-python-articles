"""How a page asks "which of these users are online?" in each design."""
import redis.asyncio as aioredis

WHERE = "presence:where"


async def online_by_gateway(r: aioredis.Redis,
                            users: list[str]) -> dict[str, bool]:
    """Online = mapped to a gateway whose lease is alive. Two round trips."""
    gateways = await r.hmget(WHERE, users)
    distinct = sorted({g for g in gateways if g})
    leases = await r.mget([f"gw:{g}:alive" for g in distinct])
    alive = dict(zip(distinct, leases))
    return {u: bool(g and alive.get(g)) for u, g in zip(users, gateways)}


async def online_by_window(r: aioredis.Redis, users: list[str], now: float,
                           window: float) -> dict[str, bool]:
    """Online = last heartbeat inside the window. One round trip."""
    scores = await r.zmscore("presence:online", users)
    return {u: s is not None and s > now - window
            for u, s in zip(users, scores)}
