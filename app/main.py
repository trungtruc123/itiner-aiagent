"""Travel Planner Agent – FastAPI application entry-point.

Lifecycle
─────────
1. **Startup** – logging → database → memory (Redis / Neo4j / Mem0) →
   Prometheus metadata → LangGraph pre-warm → mark *ready*.
2. **Running** – serve HTTP traffic; health probes report live state.
3. **Shutdown** – mark *shutting_down* → close memory → close database →
   mark *stopped*.

Every subsystem init is wrapped in its own try/except so a single backend
being unavailable degrades the app instead of crashing it.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
# Eagerly import openai to avoid _DeadlockError on lazy import in async context
import openai  # noqa: F401

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.health import router as health_router
from app.api.v1.sessions import router as sessions_router
from app.core.app_state import AppPhase, AppState, ServiceStatus, app_state
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.metrics import APP_INFO, metrics_endpoint
from app.core.middleware import RequestContextMiddleware
from app.services.database import close_db, init_db
from app.services.memory import close_memory, init_memory

logger = structlog.get_logger(__name__)


# ───────────────────────── startup helpers ─────────────────────────────
async def _startup_logging() -> None:
    """Configure structured logging as the very first step."""
    setup_logging()
    logger.info(
        "application_starting",
        environment=settings.ENVIRONMENT.value,
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
    )


async def _startup_database(state: AppState) -> None:
    """Initialise the async Postgres pool and run DDL migrations."""
    try:
        t0 = time.perf_counter()
        await init_db()
        elapsed = time.perf_counter() - t0
        state.mark_service("database", ServiceStatus.HEALTHY)
        logger.info("database_ready", duration=round(elapsed, 3))
    except Exception:
        state.mark_service("database", ServiceStatus.UNHEALTHY)
        logger.exception("database_startup_failed")


async def _startup_memory(state: AppState) -> None:
    """Bring up Redis, Neo4j, and Mem0 (each failure is non-fatal)."""
    try:
        t0 = time.perf_counter()
        await init_memory()
        elapsed = time.perf_counter() - t0

        # Inspect the module-level flags set by init_memory()
        from app.services.memory import _mem0_client, _neo4j_driver, _redis_client

        state.mark_service(
            "redis",
            ServiceStatus.HEALTHY if _redis_client else ServiceStatus.UNHEALTHY,
        )
        state.mark_service(
            "neo4j",
            ServiceStatus.HEALTHY if _neo4j_driver else ServiceStatus.UNHEALTHY,
        )
        state.mark_service(
            "mem0",
            ServiceStatus.HEALTHY if _mem0_client else ServiceStatus.UNHEALTHY,
        )

        logger.info("memory_services_ready", duration=round(elapsed, 3))
    except Exception:
        state.mark_service("redis", ServiceStatus.UNHEALTHY)
        state.mark_service("neo4j", ServiceStatus.UNHEALTHY)
        state.mark_service("mem0", ServiceStatus.UNHEALTHY)
        logger.exception("memory_startup_failed")


async def _startup_prometheus() -> None:
    """Publish static app metadata into Prometheus."""
    APP_INFO.info(
        {
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT.value,
        }
    )
    logger.info("prometheus_metadata_set")


async def _startup_langgraph(state: AppState) -> None:
    """Pre-compile the LangGraph agent so the first request is fast."""
    try:
        t0 = time.perf_counter()
        from app.core.langgraph.graph import create_compiled_graph

        await create_compiled_graph()
        elapsed = time.perf_counter() - t0
        state.mark_service("langgraph", ServiceStatus.HEALTHY)
        logger.info("langgraph_prewarmed", duration=round(elapsed, 3))
    except Exception:
        state.mark_service("langgraph", ServiceStatus.DEGRADED)
        logger.exception("langgraph_prewarm_failed")


# ───────────────────────── shutdown helpers ─────────────────────────────
async def _shutdown_memory() -> None:
    try:
        await close_memory()
        logger.info("memory_services_closed")
    except Exception:
        logger.exception("memory_shutdown_error")


async def _shutdown_database() -> None:
    try:
        await close_db()
        logger.info("database_closed")
    except Exception:
        logger.exception("database_shutdown_error")


# ───────────────────────── lifespan ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage full application lifecycle with per-subsystem error isolation."""
    startup_start = time.perf_counter()
    app_state.phase = AppPhase.STARTING

    # ── STARTUP (order matters) ──────────────────────────────────────
    await _startup_logging()
    await _startup_database(app_state)
    await _startup_memory(app_state)
    await _startup_prometheus()
    await _startup_langgraph(app_state)

    # Finalise startup
    app_state.started_at = time.time()
    app_state.phase = AppPhase.READY
    startup_elapsed = time.perf_counter() - startup_start

    logger.info(
        "application_ready",
        startup_seconds=round(startup_elapsed, 3),
        services={k: v.value for k, v in app_state.services.items()},
    )

    # ── SERVE ────────────────────────────────────────────────────────
    yield

    # ── SHUTDOWN ─────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    app_state.phase = AppPhase.SHUTTING_DOWN

    await _shutdown_memory()
    await _shutdown_database()

    app_state.phase = AppPhase.STOPPED
    logger.info(
        "application_stopped",
        total_uptime_seconds=round(app_state.uptime_seconds, 2),
    )


# ───────────────────────── FastAPI app ─────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered travel planning agent",
    lifespan=lifespan,
)

# Middleware (applied bottom-up: CORS first, then request context)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
api_prefix = settings.API_PREFIX
app.include_router(health_router, prefix=api_prefix)
app.include_router(auth_router, prefix=api_prefix)
app.include_router(sessions_router, prefix=api_prefix)
app.include_router(chat_router, prefix=api_prefix)

# Prometheus metrics
app.add_route("/metrics", metrics_endpoint)


# ───────────────────────── CLI entry-point ─────────────────────────────
def start() -> None:
    """Entry point for the ``serve`` console script."""
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development,
    )
