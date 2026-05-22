"""
Redis-based rate limiter using sliding window sorted sets.
Rate limits by client IP (supports X-Forwarded-For for proxied requests).
All config via env vars — nothing hardcoded.

Degrades gracefully: if Redis is unavailable, requests pass through.
"""
import os
import time

import redis.asyncio as aioredis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))          # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))    # window in seconds

# Paths exempt from rate limiting
EXEMPT_PATHS = {"/health", "/", "/docs", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):

    def __init__(self, app):
        super().__init__(app)
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    REDIS_URL, decode_responses=True, socket_connect_timeout=2
                )
                await self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP — supports proxy headers."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        r = await self._get_redis()
        if r is None:
            # Redis unavailable — degrade gracefully, allow request through
            return await call_next(request)

        ip = self._get_client_ip(request)
        key = f"ratelimit:ip:{ip}"
        now = time.time()

        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)  # remove expired
            pipe.zadd(key, {f"{now}": now})                         # add current
            pipe.zcard(key)                                          # count in window
            pipe.expire(key, RATE_LIMIT_WINDOW + 1)                 # auto-cleanup
            results = await pipe.execute()

            request_count = results[2]

            if request_count > RATE_LIMIT_MAX:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "detail": f"Maximum {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW}s",
                        "retry_after_seconds": RATE_LIMIT_WINDOW,
                    },
                    headers={
                        "Retry-After": str(RATE_LIMIT_WINDOW),
                        "X-RateLimit-Limit": str(RATE_LIMIT_MAX),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            remaining = max(0, RATE_LIMIT_MAX - request_count)
            response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Window"] = str(RATE_LIMIT_WINDOW)
            return response

        except Exception:
            # Redis error mid-request — allow through
            return await call_next(request)
