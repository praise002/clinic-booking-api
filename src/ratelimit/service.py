import logging
import math
from pathlib import Path
import uuid

from redis.exceptions import RedisError

from src.core.exceptions import TooManyRequests
from src.ratelimit import constants
from src.redis_client import redis_client

log = logging.getLogger(__name__)

KEY_PREFIX = "ratelimit:"
_sliding_window = redis_client.register_script(
    Path(__file__).with_name("sliding_window.lua").read_text()
)


def normalise_email(email: object) -> str | None:
    """The key attempts are counted under, or None when there's no usable email."""
    if not isinstance(email, str) or not email.strip():
        return None
    return email.strip().lower()


async def check_and_record(email: str) -> None:
    """Record one booking attempt for this email, or raise TooManyRequests (429).

    Every attempt counts, whatever its outcome later. If Redis can't be reached the attempt
    is allowed (fail open): the rate limit is a guard against spam, while booking
    correctness lives in Postgres and never depends on Redis.
    """
    window_ms = constants.WINDOW_SECONDS * 1000
    try:
        wait_ms = await _sliding_window(
            keys=[f"{KEY_PREFIX}{email}"],
            args=[window_ms, constants.LIMIT, uuid.uuid4().hex],
            client=redis_client,
        )
    except (RedisError, OSError) as error:
        log.warning("rate limit skipped, Redis unavailable: %s", error)
        return
    if wait_ms >= 0:
        raise TooManyRequests(retry_after=max(1, math.ceil(wait_ms / 1000)))


async def clear_all() -> None:
    """Forget every email's attempts (part of POST /reset)."""
    try:
        keys = [key async for key in redis_client.scan_iter(match=f"{KEY_PREFIX}*", count=500)]
        if keys:
            await redis_client.delete(*keys)
    except (RedisError, OSError) as error:
        log.warning("rate limits not cleared, Redis unavailable: %s", error)
