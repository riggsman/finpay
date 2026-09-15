"""Redis-backed fixed-window rate limiting.

Fails open: if Redis is unavailable or misbehaves, requests are allowed so a
cache outage never takes down authentication.
"""
import redis

from app.core.config import settings
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger

logger = get_logger("finpay.ratelimit")

_client = None
_client_failed = False


def _redis():
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    try:
        _client = redis.from_url(settings.REDIS_URL, socket_timeout=0.5,
                                 socket_connect_timeout=0.5, decode_responses=True)
        _client.ping()
    except Exception as exc:  # pragma: no cover - depends on runtime redis
        logger.warning("Rate limiter Redis unavailable; failing open: %s", exc)
        _client = None
        _client_failed = True
    return _client


def check_rate_limit(scope: str, identifier: str, limit: int, window: int) -> None:
    """Increment the counter for (scope, identifier) and raise RateLimitError
    when the limit within the window is exceeded."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    client = _redis()
    if client is None:
        return  # fail open
    key = f"rl:{scope}:{identifier}"
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window)
        if count > limit:
            ttl = client.ttl(key)
            raise RateLimitError(
                "Too many requests. Please try again later.",
                code="RATE_LIMITED",
                details={"retry_after_seconds": ttl if ttl and ttl > 0 else window},
            )
    except RateLimitError:
        raise
    except Exception as exc:  # pragma: no cover - fail open on redis errors
        logger.warning("Rate limit check failed open: %s", exc)
