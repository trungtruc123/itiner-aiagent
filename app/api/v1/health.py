"""Health / readiness / liveness probes.

Three endpoints follow the Kubernetes probe convention:

* ``GET /health``       – **deep check**: live-probes every backend and
  returns per-service status with uptime metadata.
* ``GET /health/ready`` – **readiness probe**: returns 200 only after the
  startup sequence has finished (``app_state.phase == READY``).
* ``GET /health/live``  – **liveness probe**: always returns 200 as long
  as the process is running.
"""

from __future__ import annotations

from typing import Any, Dict

import structlog
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.app_state import AppPhase, ServiceStatus, app_state
from app.services.database import async_session_factory
from app.services.memory import _redis_client

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(response: Response) -> Dict[str, Any]:
    """Deep health check — live-probes every backend and merges with cached
    startup state so newly-broken connections are detected immediately."""

    live_checks: Dict[str, ServiceStatus] = {}

    # ── Database ──────────────────────────────────────────────────────
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        live_checks["database"] = ServiceStatus.HEALTHY
    except Exception:
        live_checks["database"] = ServiceStatus.UNHEALTHY

    # ── Redis ─────────────────────────────────────────────────────────
    try:
        if _redis_client:
            await _redis_client.ping()
            live_checks["redis"] = ServiceStatus.HEALTHY
        else:
            live_checks["redis"] = ServiceStatus.NOT_CONFIGURED
    except Exception:
        live_checks["redis"] = ServiceStatus.UNHEALTHY

    # Merge live probes back into the singleton so other parts of the app
    # see up-to-date values without polling themselves.
    for svc, svc_status in live_checks.items():
        app_state.mark_service(svc, svc_status)

    # ── Overall verdict ───────────────────────────────────────────────
    all_ok = all(
        v in (ServiceStatus.HEALTHY, ServiceStatus.NOT_CONFIGURED)
        for v in app_state.services.values()
    )
    overall = "healthy" if all_ok else "degraded"

    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall,
        "phase": app_state.phase.value,
        "uptime_seconds": round(app_state.uptime_seconds, 2),
        "services": {k: v.value for k, v in app_state.services.items()},
    }


@router.get("/health/ready")
async def readiness_check(response: Response) -> Dict[str, Any]:
    """Readiness probe — returns 200 *only* when startup is complete.

    Kubernetes uses this to decide whether to route traffic to the pod.
    """
    if app_state.phase != AppPhase.READY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "phase": app_state.phase.value,
        }

    return {
        "status": "ready",
        "phase": app_state.phase.value,
        "uptime_seconds": round(app_state.uptime_seconds, 2),
    }


@router.get("/health/live")
async def liveness_check() -> Dict[str, str]:
    """Liveness probe — always 200 while the process is running.

    Kubernetes uses this to decide whether to *restart* the pod.
    """
    return {"status": "alive"}
