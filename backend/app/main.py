from __future__ import annotations

import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import get_settings
from .db import init_db
from .domain.state_machine import InvalidTransition
from .health import router as health_router

settings = get_settings()
app = FastAPI(
    title="EquiTask AI",
    description="Uncertainty-aware, fair and failure-resilient volunteer coordination API",
    version="0.1.0",
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.exception_handler(InvalidTransition)
async def invalid_transition_handler(_: Request, exc: InvalidTransition) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse as _JSONResponse


class SimpleRateLimit(BaseHTTPMiddleware):
    """Small in-process fixed-window limiter; replace with gateway/Redis for multi-instance deployment."""

    def __init__(self, app, limit: int = 120, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return _JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        bucket.append(now)
        return await call_next(request)


app.add_middleware(SimpleRateLimit, limit=settings.request_rate_limit)
app.include_router(router)
app.include_router(health_router)  # root-level /health for load balancers / container probes

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
