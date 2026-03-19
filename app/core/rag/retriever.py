import json
from typing import Optional

import structlog
from langchain_core.tools import tool
from langchain_community.vectorstores import PGVector
from langchain_openai import OpenAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.metrics import AGENT_STEP_COUNT
from app.services.memory import cache_get, cache_set

logger = structlog.get_logger(__name__)

_vectorstore: Optional[PGVector] = None


async def init_rag_retriever() -> None:
    global _vectorstore

    try:
        embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        _vectorstore = PGVector(
            collection_name="hotel_policies",
            connection_string=settings.DATABASE_SYNC_URL,
            embedding_function=embeddings,
        )
        logger.info("rag_retriever_initialized")
    except Exception:
        logger.exception("rag_retriever_initialization_failed")


def get_vectorstore() -> Optional[PGVector]:
    return _vectorstore


@tool
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def query_hotel_policies(
    question: str,
    hotel_name: Optional[str] = None,
) -> str:
    """Query hotel policies and regulations using RAG.

    Use this tool to answer questions about specific hotel policies such as
    check-in/check-out times, cancellation rules, pet policies, amenities, etc.

    Args:
        question: The question about hotel policies.
        hotel_name: Optional hotel name to filter results.

    Returns:
        A JSON string with relevant policy information and source context.
    """
    AGENT_STEP_COUNT.labels(step_name="query_hotel_policies", status="started").inc()

    logger.info(
        "hotel_policy_query_started",
        question=question,
        hotel_name=hotel_name,
    )

    cache_key = f"rag:{question}:{hotel_name or 'all'}"
    cached = await cache_get(cache_key)
    if cached:
        AGENT_STEP_COUNT.labels(step_name="query_hotel_policies", status="completed").inc()
        return cached

    if not _vectorstore:
        logger.warning("rag_vectorstore_not_initialized")
        return json.dumps({
            "error": "Hotel policy database is not yet initialized. Please try again later.",
            "sources": [],
        })

    search_kwargs = {"k": 4}
    if hotel_name:
        search_kwargs["filter"] = {"hotel_name": hotel_name}

    try:
        docs = _vectorstore.similarity_search(
            question,
            **search_kwargs,
        )
    except Exception:
        logger.exception("rag_similarity_search_failed")
        return json.dumps({
            "error": "Failed to search hotel policies.",
            "sources": [],
        })

    sources = []
    context_parts = []
    for doc in docs:
        source = {
            "content": doc.page_content,
            "hotel_name": doc.metadata.get("hotel_name", "Unknown"),
            "policy_type": doc.metadata.get("policy_type", "general"),
        }
        sources.append(source)
        context_parts.append(doc.page_content)

    result = json.dumps({
        "question": question,
        "context": "\n\n---\n\n".join(context_parts),
        "sources": sources,
        "total_sources": len(sources),
        "note": "Answers are based on retrieved hotel policy documents. Information is specific to each hotel.",
    }, indent=2)

    await cache_set(cache_key, result, ttl=900)
    AGENT_STEP_COUNT.labels(step_name="query_hotel_policies", status="completed").inc()

    logger.info(
        "hotel_policy_query_completed",
        sources_found=len(sources),
    )
    return result
