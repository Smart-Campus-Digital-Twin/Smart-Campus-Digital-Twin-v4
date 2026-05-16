"""
Custom ASGI middleware:
  - SlowAPI rate-limiting (REST + WS)
  - Structured JSON request logging (request_id, path, status, duration_ms)
  - Security response headers
  - Server header removal
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.core.config import settings

logger = logging.getLogger("api.access")

# ---------------------------------------------------------------------------
# Rate limiter — shared singleton imported by routers
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_rest])


def setup_rate_limiter(app: FastAPI) -> None:
    """Attach slowapi state and exception handler to the FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Request logging + security headers middleware
# ---------------------------------------------------------------------------

async def logging_middleware(request: Request, call_next: Callable) -> Response:
    """
    Per-request structured logging and security header injection.

    Adds X-Request-ID to both the request state and response headers
    so downstream logs can be correlated.
    """
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.monotonic()

    response: Response = await call_next(request)

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    user_id = getattr(request.state, "user_id", None)
    building_id = getattr(request.state, "building_id", None)

    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "building_id": building_id,
            "client_ip": get_remote_address(request),
        },
    )

    # Security headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    with contextlib.suppress(KeyError):
        del response.headers["server"]
    return response
