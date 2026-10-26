"""Rate limiting primitives."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    """Rate limit decision."""

    allowed: bool
    retry_after: int | None


class SlidingWindowLimiter:
    """Thread-safe sliding-window limiter with injectable monotonic clock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._events: dict[str, deque[float]] = {}

    def check(self, key: str, calls: int, period_seconds: int) -> RateLimitDecision:
        """Record one event and return whether it is allowed."""
        now = self._clock()
        with self._lock:
            queue = self._events.setdefault(key, deque())
            boundary = now - period_seconds
            while queue and queue[0] <= boundary:
                queue.popleft()
            if len(queue) >= calls:
                retry_after = int(max(1, period_seconds - (now - queue[0])))
                return RateLimitDecision(False, retry_after)
            queue.append(now)
            return RateLimitDecision(True, None)
