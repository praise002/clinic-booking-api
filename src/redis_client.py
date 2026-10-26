from redis.asyncio import Redis

from src.config import settings

# Short timeouts: if Redis hangs, the rate limit gives up quickly and the booking goes
# ahead (fail open) instead of every booking waiting on Redis. rediss:// URLs (Upstash)
# use TLS.
redis_client = Redis.from_url(
    settings.REDIS_URL,
    socket_connect_timeout=settings.REDIS_TIMEOUT_SECONDS,
    socket_timeout=settings.REDIS_TIMEOUT_SECONDS,
)
