import time

from redis.asyncio import Redis

from app.config import settings


async def check_ingestion_rate(redis: Redis, client_key: str = "global") -> bool:
    """Fixed window rate limit: max N requests per minute. Returns True if allowed."""
    window = 60
    limit = settings.ingestion_rate_per_minute
    now = int(time.time())
    bucket = now // window
    key = f"rl:ingest:{client_key}:{bucket}"
    n = await redis.incr(key)
    if n == 1:
        await redis.expire(key, window + 1)
    return n <= limit
