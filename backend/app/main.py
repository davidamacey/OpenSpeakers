"""OpenSpeakers FastAPI application entry point.

Production-quality setup:
  - Request ID tracking (X-Request-ID header)
  - Structured error responses
  - CORS with explicit origin list
  - Health check at /health (Docker-compatible)
  - Alembic migrations on startup
  - Graceful shutdown
  - WebSocket endpoint for real-time job progress
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.api.endpoints.system import router as system_router
from app.api.websockets import ws_router
from app.core.config import settings
from app.middleware.request_id import RequestIDMiddleware

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting OpenSpeakers backend (env=%s)", settings.ENVIRONMENT)

    # Run DB migrations
    try:
        from app.db.migrations import run_migrations

        run_migrations()
    except Exception:
        logger.exception(
            "Migration failed — the database may be unavailable. Continuing."
        )

    # Ensure audio output directory exists
    from pathlib import Path

    Path(settings.AUDIO_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    logger.info("OpenSpeakers backend ready")
    yield
    logger.info("OpenSpeakers backend shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenSpeakers",
    description="Unified TTS and voice cloning API — VibeVoice, Fish Speech, Qwen3, Kokoro",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware ─────────────────────────────────────────────────────────────────

app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5200",  # Mapped dev port
        "http://localhost:3000",
        "http://frontend:5173",  # Docker network
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# ── Exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    logger.warning("ValueError in %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=422,
        content={
            "error": str(exc),
            "status_code": 422,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "Unhandled exception [request_id=%s] %s %s",
        request_id,
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "request_id": request_id,
        },
    )


# ── Request timing middleware (simple) ───────────────────────────────────────


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    t = time.monotonic()
    response = await call_next(request)
    elapsed_ms = int((time.monotonic() - t) * 1000)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    return response


# ── Routes ────────────────────────────────────────────────────────────────────

# System routes at root (health check for Docker)
app.include_router(system_router)

# REST API under /api
app.include_router(api_router)

# WebSocket routes (no /api prefix — proxied separately in nginx)
app.include_router(ws_router)
