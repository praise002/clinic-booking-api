from redis.asyncio import Redis

from src.config import settings

# Short timeouts: if Redis hangs, the rate limit gives up within half a second and the
# booking goes ahead (fail open) instead of every booking waiting on Redis.
redis_client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
