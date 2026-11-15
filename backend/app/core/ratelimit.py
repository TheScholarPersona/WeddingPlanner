"""Fixed-window rate limiting for sensitive endpoints (login, password reset)."""

import time
from collections import defaultdict
from typing import Protocol

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.errors import ProblemError


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Count one hit; return False when the limit for this window is exceeded."""
        ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        bucket = f"{key}:{int(time.time()) // window_seconds}"
        self._counts[bucket] += 1
        return self._counts[bucket] <= limit

    def reset(self) -> None:
        self._counts.clear()


class RedisRateLimiter:
    def __init__(self, url: str) -> None:
        self._redis: Redis = Redis.from_url(url)

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        bucket = f"ratelimit:{key}:{int(time.time()) // window_seconds}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(bucket)
            pipe.expire(bucket, window_seconds)
            count, _ = await pipe.execute()
        return int(count) <= limit


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        settings = get_settings()
        _limiter = (
            RedisRateLimiter(str(settings.redis_url))
            if settings.rate_limit_backend == "redis"
            else MemoryRateLimiter()
        )
    return _limiter


async def enforce(keys: list[str], limit: int, window_seconds: int = 60) -> None:
    limiter = get_rate_limiter()
    results = [await limiter.hit(key, limit, window_seconds) for key in keys]
    if not all(results):
        raise ProblemError(
            429,
            "rate_limited",
            "Too many attempts",
            "Please wait a minute and try again.",
        )
