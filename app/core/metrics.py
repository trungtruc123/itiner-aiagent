from prometheus_client import Counter, Histogram, Info, generate_latest
from starlette.requests import Request
from starlette.responses import Response

APP_INFO = Info("travel_planner", "Travel Planner AI Application")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

LLM_REQUEST_COUNT = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["model", "tool_name"],
)

LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["model"],
)

LLM_TOKEN_USAGE = Counter(
    "llm_token_usage_total",
    "Total LLM token usage",
    ["model", "token_type"],
)

AGENT_STEP_COUNT = Counter(
    "agent_steps_total",
    "Total agent workflow steps",
    ["step_name", "status"],
)

MEMORY_OPERATIONS = Counter(
    "memory_operations_total",
    "Total memory operations",
    ["operation", "memory_type"],
)


async def metrics_endpoint(request: Request) -> Response:
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
