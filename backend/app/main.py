from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import admin, anomalies, applications, azure, budgets, costs, dashboard, ingestion, meta, notifications, resources, savings
from app.core.config import APP_VERSION, get_settings
from app.core.db import get_engine
from app.core.errors import AppError
from app.core.logging import configure_logging, log_context

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
log = logging.getLogger("acip.api")

app = FastAPI(
    title="Azure Cost Intelligence Platform API",
    version=APP_VERSION,
    description=(
        "Reporting, comparison, anomaly, budget and ingestion APIs. All reporting reads pre-aggregated data from PostgreSQL; "
        "no endpoint calls Azure billing APIs on a dashboard request. Cost types (actual / amortized) and billing currencies "
        "are never summed together."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-ACIP-Dev-Role", "X-ACIP-Dev-Application"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    start = time.perf_counter()
    with log_context(request_id=rid):
        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - handled by exception handler
            log.exception("Unhandled error", extra={"path": request.url.path})
            raise
        dur = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        if not request.url.path.startswith("/health"):
            log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": round(dur, 1)})
        return response


def _error(status: int, code: str, message: str, details=None, request: Request | None = None) -> JSONResponse:
    rid = request.headers.get("X-Request-ID") if request else None
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details, "request_id": rid}})


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return _error(exc.status_code, exc.code, exc.message, exc.details, request)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _error(422, "validation_failed", "Request validation failed", [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()], request)


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    return _error(exc.status_code, "http_error", str(exc.detail), None, request)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("Unhandled exception", extra={"path": request.url.path})
    return _error(500, "internal_error", "An unexpected error occurred. Use the request id to find details in the logs.", None, request)


@app.get("/health/live", tags=["Health"])
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def ready():
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(exc)[:200]})
    return {"status": "ok", "schema_revision": rev, "version": APP_VERSION}


API = "/api/v1"
for r in (meta, dashboard, costs, resources, anomalies, applications, budgets, savings, notifications, ingestion, azure, admin):
    app.include_router(r.router, prefix=API)
