"""
Security middleware for the RideMate AI API.

Provides:
- API Key authentication: protects /api/v1/* endpoints behind X-API-Key header
- Rate limiting: per-IP sliding-window rate limiter to prevent abuse
- Input validation: sanitization helper for user-supplied strings

Configure via .env:
  API_KEY_REQUIRED=true/false  (default: false in dev, true in production)
  API_KEY=your-secret-key      (fallback if not set, a random key is generated)
  RATE_LIMIT_MAX=30            (max requests per window, default 30)
  RATE_LIMIT_WINDOW=60         (window in seconds, default 60)
"""

import os
import re
import time
import hashlib
import secrets
from collections import defaultdict
from typing import Callable

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_429_TOO_MANY_REQUESTS


# ── Configuration ───────────────────────────────────────────────────────

API_KEY = os.getenv("API_KEY", secrets.token_urlsafe(32))
API_KEY_REQUIRED = os.getenv("API_KEY_REQUIRED", "false").lower() == "true"
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "30"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# Public paths that skip auth (always accessible)
PUBLIC_PATHS = {"/", "/health", "/api/v1/health", "/api/v1/test", "/static", "/docs", "/openapi.json", "/redoc"}

# For demo/video purposes, generate and log the key so it's visible in terminal
if API_KEY_REQUIRED:
    print(f"\n{'='*60}")
    print(f"🔐 API Key authentication ENABLED")
    print(f"   Key: {API_KEY}")
    print(f"   Include in requests as header: X-API-Key: {API_KEY}")
    print(f"{'='*60}\n")


# ── API Key Middleware ──────────────────────────────────────────────────

class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header on protected endpoints.

    Bypassed when API_KEY_REQUIRED=false (development mode).
    Only applies to paths starting with /api/v1/.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip if auth is not required (development mode)
        if not API_KEY_REQUIRED:
            return await call_next(request)

        # Skip public paths
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        # Only protect API routes
        if not path.startswith("/api/"):
            return await call_next(request)

        # Check API key header
        provided_key = request.headers.get("X-API-Key", "")
        if not provided_key:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header. Include your API key to access this endpoint.",
            )

        if not self._verify_key(provided_key):
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Invalid API key. Request a valid key or check your configuration.",
            )

        return await call_next(request)

    def _verify_key(self, key: str) -> bool:
        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(key.encode(), API_KEY.encode())


# ── Rate Limiter Middleware ─────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by client IP.

    Tracks request counts in configurable time windows.
    Returns 429 Too Many Requests when the limit is exceeded.
    """

    def __init__(self, app, max_requests: int = RATE_LIMIT_MAX, window_seconds: int = RATE_LIMIT_WINDOW):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)
        print(f"🛡️  Rate limiter active: {max_requests} req / {window_seconds}s per IP")

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip public paths from rate limiting
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATHS):
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()

        # Clean expired entries for this IP
        self._buckets[client_ip] = [
            t for t in self._buckets[client_ip]
            if now - t < self.window_seconds
        ]

        # Check limit
        if len(self._buckets[client_ip]) >= self.max_requests:
            oldest = min(self._buckets[client_ip]) if self._buckets[client_ip] else now
            retry_after = int(self.window_seconds - (now - oldest))
            return JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Record request
        self._buckets[client_ip].append(now)
        return await call_next(request)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For proxy headers."""
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        forwarded = request.headers.get("X-Real-IP", "")
        if forwarded:
            return forwarded.strip()
        # Fall back to direct client
        if hasattr(request, "client") and request.client:
            return request.client.host
        return "unknown"


# ── Input Sanitization ──────────────────────────────────────────────────

def sanitize_input(text: str, max_length: int = 2000) -> str:
    """Sanitize user-supplied text input.

    - Strips leading/trailing whitespace
    - Truncates to max_length
    - Removes null bytes and control characters (except common whitespace)
    - Does NOT HTML-escape (the AI response is rendered in a controlled HTML page)

    Returns sanitized string.
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()[:max_length]
    # Remove null bytes and non-printable control chars (keep \n \r \t)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text


def validate_user_id(user_id: str) -> bool:
    """Verify user_id format: alphanumeric + underscore + hyphen, 1-64 chars."""
    if not user_id or not isinstance(user_id, str):
        return False
    return bool(re.match(r'^[a-zA-Z0-9_\-]{1,64}$', user_id))
