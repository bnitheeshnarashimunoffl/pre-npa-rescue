"""In-memory token-bucket rate limiting for ``/auth/login`` and ``/chat/*`` (task 5.3).

Per-process only: fine for the single-instance demo; a multi-instance deployment would need a
shared store. Login is keyed by client address plus username (slows password guessing);
chat is keyed by the authenticated user.
"""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request

from app.config import get_settings
from app.errors import ApiError


@dataclass
class TokenBucket:
    capacity: float
    refill_per_second: float
    clock: Callable[[], float] = time.monotonic
    _state: dict[str, tuple[float, float]] = field(default_factory=dict)  # key -> (tokens, at)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def take(self, key: str) -> float:
        """Consume one token for ``key``. Returns 0 if allowed, else seconds until allowed."""
        with self._lock:
            now = self.clock()
            tokens, at = self._state.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - at) * self.refill_per_second)
            if tokens >= 1:
                self._state[key] = (tokens - 1, now)
                return 0.0
            self._state[key] = (tokens, now)
            return (1 - tokens) / self.refill_per_second


def per_minute(limit: int) -> TokenBucket:
    return TokenBucket(capacity=limit, refill_per_second=limit / 60)


class RateLimits:
    """Process-wide buckets, built from settings on first use (reset in tests)."""

    _login: TokenBucket | None = None
    _chat: TokenBucket | None = None

    @classmethod
    def login(cls) -> TokenBucket:
        if cls._login is None:
            cls._login = per_minute(get_settings().login_rate_per_minute)
        return cls._login

    @classmethod
    def chat(cls) -> TokenBucket:
        if cls._chat is None:
            cls._chat = per_minute(get_settings().chat_rate_per_minute)
        return cls._chat

    @classmethod
    def reset(cls) -> None:
        cls._login = cls._chat = None


def enforce(bucket: TokenBucket, key: str) -> None:
    wait = bucket.take(key)
    if wait > 0:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Too many requests. Please wait and try again.",
            {"retry_after_seconds": math.ceil(wait)},
            headers={"Retry-After": str(math.ceil(wait))},
        )


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"
