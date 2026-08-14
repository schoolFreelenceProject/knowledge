from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        max_body_bytes: int,
        path_max_body_bytes: dict[str, int] | None = None,
    ) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes
        self.path_max_body_bytes = path_max_body_bytes or {}

    async def dispatch(self, request: Request, call_next) -> Response:
        max_body_bytes = self.path_max_body_bytes.get(
            request.url.path,
            self.max_body_bytes,
        )
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                body_size = int(content_length)
            except ValueError:
                body_size = 0

            if body_size > max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "Request body is too large. "
                            f"Maximum allowed size is {max_body_bytes} bytes."
                        )
                    },
                )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_window: int,
        window_seconds: int,
    ) -> None:
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._requests_by_key: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next) -> Response:
        if _is_rate_limit_exempt(request.url.path):
            return await call_next(request)

        retry_after = self._record_request(request)
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded."},
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )

        return await call_next(request)

    def _record_request(self, request: Request) -> float | None:
        now = time.monotonic()
        window_start = now - self.window_seconds
        key = _rate_limit_key(request)
        with self._lock:
            timestamps = self._requests_by_key[key]
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()

            if len(timestamps) >= self.requests_per_window:
                return self.window_seconds - (now - timestamps[0])

            timestamps.append(now)
            return None


def _is_rate_limit_exempt(path: str) -> bool:
    return path == "/" or path.startswith("/static") or path.startswith("/health")


def _rate_limit_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        host = forwarded_for.split(",", 1)[0].strip()
    else:
        host = request.client.host if request.client else "unknown"

    return f"{host}:{request.url.path}"
