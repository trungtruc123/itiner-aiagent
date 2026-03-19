"""Centralised application state used by health probes and the lifespan handler.

The singleton `app_state` tracks which subsystems are up so the health endpoint
can return accurate readiness / liveness information without re-probing every
backend on each request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class AppPhase(str, Enum):
    STARTING = "starting"
    READY = "ready"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    NOT_CONFIGURED = "not_configured"
    DEGRADED = "degraded"


@dataclass
class AppState:
    phase: AppPhase = AppPhase.STARTING
    started_at: float = 0.0
    services: Dict[str, ServiceStatus] = field(default_factory=dict)

    # ── convenience helpers ────────────────────────────────────────────
    def mark_service(self, name: str, status: ServiceStatus) -> None:
        self.services[name] = status

    @property
    def is_ready(self) -> bool:
        return self.phase == AppPhase.READY

    @property
    def is_healthy(self) -> bool:
        """Healthy if *all* configured services report healthy."""
        if not self.is_ready:
            return False
        return all(
            v in (ServiceStatus.HEALTHY, ServiceStatus.NOT_CONFIGURED)
            for v in self.services.values()
        )

    @property
    def uptime_seconds(self) -> float:
        if self.started_at == 0.0:
            return 0.0
        return time.time() - self.started_at

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "services": {k: v.value for k, v in self.services.items()},
        }


# Module-level singleton — imported everywhere
app_state = AppState()
