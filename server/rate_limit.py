"""Simple in-memory per-IP rate limiter for login attempts."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)

# defaults: 10 attempts / 5 minutes
WINDOW_SEC = 300
MAX_ATTEMPTS = 10


def client_ip(request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def check_login_allowed(ip: str, *, window: int = WINDOW_SEC, limit: int = MAX_ATTEMPTS) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > window:
            q.popleft()
        return len(q) < limit


def record_login_failure(ip: str) -> None:
    now = time.monotonic()
    with _lock:
        _hits[ip].append(now)


def clear_login_failures(ip: str) -> None:
    with _lock:
        _hits.pop(ip, None)


def reset_for_tests() -> None:
    with _lock:
        _hits.clear()
