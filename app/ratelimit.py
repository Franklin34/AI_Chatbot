import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding-window limiter keyed by client. `per_minute=0` disables it."""

    def __init__(self, per_minute: int):
        self._limit = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self._limit <= 0:
            return True
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True
