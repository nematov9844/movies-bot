from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.rate_limit import limiter
from app.api.routes import (
    admins,
    audit_logs,
    auth,
    broadcasts,
    channels,
    health,
    movies,
    premium,
    series,
    stats,
    users,
)
from app.api.routes import settings as settings_routes
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.core.sentry import setup_sentry
from app.database.session import async_session_factory
from app.services.admin.admin_service import AdminService
from app.services.settings.settings_service import SettingsService
from app.services.stats.stats_service import increment_api_requests, increment_errors

logger = get_logger(__name__)

# Before the FastAPI app is constructed: Sentry's Starlette/FastAPI
# integrations only auto-enable if sentry_sdk.init() has already run by the
# time the app object is created.
setup_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("api_starting", environment=settings.environment)
    async with async_session_factory() as session:
        await AdminService(session).ensure_owner_seeded()
        await session.commit()
    yield
    logger.info("api_stopping")


app = FastAPI(title="Movie Platform API", version="0.1.0", lifespan=lifespan)

# Phase 15: 60/min default (set on the Limiter itself), 5/min on login
# specifically (@limiter.limit override in auth.py).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(movies.router)
app.include_router(series.router)
app.include_router(users.router)
app.include_router(channels.router)
app.include_router(premium.router)
app.include_router(broadcasts.router)
app.include_router(settings_routes.router)
app.include_router(stats.router)
app.include_router(audit_logs.router)
app.include_router(admins.router)

# Phase 14: standard HTTP metrics (request count/latency/status) at
# GET /metrics, scraped by prometheus.yml's movie_platform_api job.
Instrumentator().instrument(app).expose(app)


@app.middleware("http")
async def count_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Counts every request in Phase 10's live ``stats:today:api_requests`` Redis counter."""
    await increment_api_requests()
    return await call_next(request)


@app.middleware("http")
async def enforce_admin_ip_whitelist(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Enforces the ``admin_ip_whitelist`` setting (comma-separated IPs, empty = disabled).

    Applies to every ``/api/*`` route, including login — an IP not on the
    list shouldn't even get a chance to guess a password — but not
    ``/health``/``/metrics``, which internal infra/monitoring must always
    be able to reach regardless of who's allowed to administer the panel.

    Reads ``request.client.host`` — behind a reverse proxy (Phase 18's
    nginx), that's only the real client IP if the proxy forwards it and
    Uvicorn runs with ``--proxy-headers`` (or an equivalent
    ``ProxyHeadersMiddleware``); this deliberately doesn't parse
    ``X-Forwarded-For`` itself, since a client-supplied header can't be
    trusted without that reverse-proxy configuration already in place.

    Returns the rejection directly as a ``JSONResponse`` rather than
    raising ``HTTPException``: this runs as an ``@app.middleware("http")``
    function, which sits *outside* Starlette's ``ExceptionMiddleware`` in
    the stack FastAPI builds — an ``HTTPException`` raised here would miss
    FastAPI's built-in per-status-code handling entirely and instead hit
    this file's catch-all ``Exception`` handler, turning a 403 into a
    misleading generic 500.
    """
    if request.url.path.startswith("/api/"):
        async with async_session_factory() as session:
            raw = await SettingsService(session).get("admin_ip_whitelist")
        allowed = {ip.strip() for ip in (raw or "").split(",") if ip.strip()}
        if allowed:
            client_ip = request.client.host if request.client else None
            if client_ip not in allowed:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Bu IP manzildan admin API'ga kirish taqiqlangan"},
                )

    return await call_next(request)


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so an unhandled exception still counts in today's live ``errors`` stat.

    FastAPI's default behavior for an uncaught exception is a bare-bones
    500 with no logging or stats visibility; this keeps that same 500
    response but adds both.
    """
    logger.exception("api_unhandled_error", path=request.url.path, error=str(exc))
    await increment_errors()
    sentry_sdk.capture_exception(exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
