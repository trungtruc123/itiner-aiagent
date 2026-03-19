import os
import time

import structlog
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.metrics import LLM_REQUEST_COUNT, LLM_REQUEST_DURATION, LLM_TOKEN_USAGE

logger = structlog.get_logger(__name__)

# Langfuse v4 reads credentials from environment variables
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.LANGFUSE_PUBLIC_KEY)
os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.LANGFUSE_SECRET_KEY)
os.environ.setdefault("LANGFUSE_HOST", settings.LANGFUSE_HOST)


def get_langfuse_handler(
    session_id: str | None = None,
    user_id: str | None = None,
    trace_name: str = "travel_planner",
) -> LangfuseCallbackHandler:
    # Langfuse v4 CallbackHandler picks up credentials from env vars.
    # session_id / user_id / trace_name are passed via trace_context or
    # set as metadata after creation.
    handler = LangfuseCallbackHandler()
    return handler


def get_llm(
    model: str | None = None,
    temperature: float | None = None,
    streaming: bool = True,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.LLM_MODEL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        api_key=settings.OPENAI_API_KEY,
        streaming=streaming,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
)
async def invoke_llm(
    llm: ChatOpenAI,
    messages: list,
    session_id: str | None = None,
    user_id: str | None = None,
    tool_name: str = "general",
) -> str:
    start_time = time.perf_counter()

    try:
        langfuse_handler = get_langfuse_handler(
            session_id=session_id,
            user_id=user_id,
        )

        response = await llm.ainvoke(
            messages,
            config={"callbacks": [langfuse_handler]},
        )

        duration = time.perf_counter() - start_time

        LLM_REQUEST_COUNT.labels(model=llm.model_name, tool_name=tool_name).inc()
        LLM_REQUEST_DURATION.labels(model=llm.model_name).observe(duration)

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            LLM_TOKEN_USAGE.labels(
                model=llm.model_name, token_type="input"
            ).inc(response.usage_metadata.get("input_tokens", 0))
            LLM_TOKEN_USAGE.labels(
                model=llm.model_name, token_type="output"
            ).inc(response.usage_metadata.get("output_tokens", 0))

        logger.info(
            "llm_invocation_completed",
            model=llm.model_name,
            tool_name=tool_name,
            duration=round(duration, 4),
        )

        return response.content

    except Exception as exc:
        logger.exception(
            "llm_invocation_failed",
            model=llm.model_name,
            tool_name=tool_name,
            error=str(exc),
        )
        raise
