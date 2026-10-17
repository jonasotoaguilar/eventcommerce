"""In-process sliding-window rate limiting for IAM credential endpoints.

State lives on the FastAPI app instance (never a module global) so every
fresh app gets empty buckets. Each key keeps its own attempt timestamps;
expired entries are pruned on every check to bound bucket growth.
"""

import math
import time
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.modules.iam.api.schemas import LoginRequest, RegisterRequest
from app.shared.config.settings import get_settings

FALLBACK_HOST = "unknown"
LOGIN_LIMIT_DETAIL = "Too many login attempts, try again later"
REGISTER_LIMIT_DETAIL = "Too many registration attempts, try again later"


class RateLimiter:
    """Sliding-window limiter keyed by an opaque string."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.clock = clock
        self._attempts: dict[str, list[float]] = {}

    @property
    def tracked_key_count(self) -> int:
        """Keys holding a live attempt; fully expired keys are evicted on read."""
        now = self.clock()
        expired = [
            key
            for key, seen in self._attempts.items()
            if all(moment <= now - self.window_seconds for moment in seen)
        ]
        for key in expired:
            del self._attempts[key]
        return len(self._attempts)

    def check_and_record(self, key: str) -> int:
        """Record an attempt; return 0 when allowed, else whole seconds to wait."""
        now = self.clock()
        bucket = [
            seen
            for seen in self._attempts.get(key, [])
            if seen > now - self.window_seconds
        ]
        if not bucket:
            self._attempts.pop(key, None)
        if len(bucket) >= self.max_attempts:
            self._attempts[key] = bucket
            return max(math.ceil(bucket[0] + self.window_seconds - now), 1)
        bucket.append(now)
        self._attempts[key] = bucket
        return 0


def login_key(host: str, email: str) -> str:
    return f"login:{host}:{email.strip().lower()}"


def login_host_key(host: str) -> str:
    return f"login-host:{host}"


def register_key(host: str) -> str:
    return f"register:{host}"


def client_host(request: Request) -> str:
    """Best-effort origin host; a missing client shares one fallback bucket."""
    client = request.client
    if client is None:
        return FALLBACK_HOST
    host = client.host if hasattr(client, "host") else client[0]
    return host or FALLBACK_HOST


def _limiter(request: Request, attr: str) -> RateLimiter:
    limiter = getattr(request.app.state, attr, None)
    if limiter is None:
        settings = get_settings()
        if attr == "login_host_limiter":
            limiter = RateLimiter(
                settings.login_rate_limit_host_attempts,
                settings.login_rate_limit_window_seconds,
            )
        elif attr == "login_limiter":
            limiter = RateLimiter(
                settings.login_rate_limit_attempts,
                settings.login_rate_limit_window_seconds,
            )
        else:
            limiter = RateLimiter(
                settings.register_rate_limit_attempts,
                settings.register_rate_limit_window_seconds,
            )
        setattr(request.app.state, attr, limiter)
    return limiter


def _reject(retry_after: int, detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after)},
    )


async def enforce_login_rate_limit(request: Request, body: LoginRequest) -> None:
    # Per-account bucket first: its rejection keeps the established wait,
    # and the shared detail hides which bucket tripped.
    host = client_host(request)
    retry_after = _limiter(request, "login_limiter").check_and_record(
        login_key(host, str(body.email))
    )
    if retry_after:
        _reject(retry_after, LOGIN_LIMIT_DETAIL)
    host_retry_after = _limiter(request, "login_host_limiter").check_and_record(
        login_host_key(host)
    )
    if host_retry_after:
        _reject(host_retry_after, LOGIN_LIMIT_DETAIL)


async def enforce_register_rate_limit(request: Request, body: RegisterRequest) -> None:
    retry_after = _limiter(request, "register_limiter").check_and_record(
        register_key(client_host(request))
    )
    if retry_after:
        _reject(retry_after, REGISTER_LIMIT_DETAIL)
