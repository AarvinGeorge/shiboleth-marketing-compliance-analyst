"""
meta:
  purpose: Public-demo hardening primitives (deployment plan 2026-07-13):
           a dependency-free sliding-window rate limiter keyed by client IP
           and the server-side page-cap clamp. Env-driven via Settings; all
           defaults keep dev behavior unchanged (limiter off, cap 20,
           nothing protected).
  contract: RateLimiter(limit, window_seconds, clock).allow(key) -> bool;
            limit 0 disables. effective_page_cap(requested, settings) ->
            min(requested, settings.page_cap_max). client_key(request)
            prefers the first X-Forwarded-For hop (Caddy fronts the API in
            prod and the API port is never exposed, so the header is
            trustworthy there).
  deps: stdlib only (time, collections).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    """In-memory sliding-window limiter. Per-process by design: the demo
    runs a single API container, so no shared store is warranted."""

    def __init__(self, limit: int, window_seconds: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True


def effective_page_cap(requested: int, settings) -> int:
    return min(requested, settings.page_cap_max)


def client_key(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
