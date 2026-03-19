import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time

            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
            ).inc()
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration)

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{duration:.4f}"

            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration=round(duration, 4),
            )
            return response

        except Exception as exc:
            duration = time.perf_counter() - start_time
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=500,
            ).inc()

            logger.exception(
                "request_failed",
                duration=round(duration, 4),
                error=str(exc),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
