from typing import Any, Dict, List, Optional

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.metrics import MEMORY_OPERATIONS

logger = structlog.get_logger(__name__)

_mem0_client = None
_redis_client = None
_neo4j_driver = None


async def init_memory() -> None:
    global _mem0_client, _redis_client, _neo4j_driver

    # Mem0 sub-components (embedder, etc.) may look up the key from the
    # environment even when we pass it explicitly in the config, so make
    # sure it is always available as an env-var.
    import os
    os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY)

    try:
        from mem0 import Memory

        mem0_config = {
            "vector_store": {
                "provider": "pgvector",
                "config": {
                    "connection_string": settings.DATABASE_SYNC_URL,
                    "collection_name": settings.MEM0_COLLECTION_NAME,
                },
            },
            "graph_store": {
                "provider": "neo4j",
                "config": {
                    "url": settings.NEO4J_URI,
                    "username": settings.NEO4J_USER,
                    "password": settings.NEO4J_PASSWORD,
                    "database": settings.NEO4J_DATABASE,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": settings.LLM_MODEL,
                    "api_key": settings.OPENAI_API_KEY,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "api_key": settings.OPENAI_API_KEY,
                },
            },
        }
        _mem0_client = Memory.from_config(mem0_config)
        logger.info("mem0_initialized")
    except Exception:
        logger.exception("mem0_initialization_failed")

    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
        await _redis_client.ping()
        logger.info("redis_connected")
    except Exception:
        logger.exception("redis_connection_failed")

    try:
        from neo4j import AsyncGraphDatabase

        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        logger.info("neo4j_connected")
    except Exception:
        logger.exception("neo4j_connection_failed")


async def close_memory() -> None:
    global _redis_client, _neo4j_driver

    if _redis_client:
        await _redis_client.close()
        logger.info("redis_connection_closed")

    if _neo4j_driver:
        await _neo4j_driver.close()
        logger.info("neo4j_connection_closed")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def add_memory(
    user_id: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not _mem0_client:
        logger.warning("mem0_not_initialized")
        return {}

    try:
        result = _mem0_client.add(
            content,
            user_id=user_id,
            metadata=metadata or {},
        )
        MEMORY_OPERATIONS.labels(operation="add", memory_type="long_term").inc()
        logger.info("memory_added", user_id=user_id)
        return result
    except Exception:
        logger.exception("memory_add_failed", user_id=user_id)
        return {}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def search_memory(
    user_id: str,
    query: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    if not _mem0_client:
        logger.warning("mem0_not_initialized")
        return []

    try:
        results = _mem0_client.search(
            query,
            user_id=user_id,
            limit=limit,
        )
        MEMORY_OPERATIONS.labels(operation="search", memory_type="long_term").inc()
        logger.info("memory_searched", user_id=user_id, results_count=len(results))
        return results
    except Exception:
        logger.exception("memory_search_failed", user_id=user_id)
        return []


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def get_user_memories(user_id: str) -> List[Dict[str, Any]]:
    if not _mem0_client:
        return []

    try:
        results = _mem0_client.get_all(user_id=user_id)
        MEMORY_OPERATIONS.labels(operation="get", memory_type="long_term").inc()
        return results
    except Exception:
        logger.exception("memory_get_failed", user_id=user_id)
        return []


async def cache_set(key: str, value: str, ttl: int = 300) -> bool:
    if not _redis_client:
        return False

    try:
        await _redis_client.setex(key, ttl, value)
        MEMORY_OPERATIONS.labels(operation="set", memory_type="short_term").inc()
        return True
    except Exception:
        logger.exception("cache_set_failed", key=key)
        return False


async def cache_get(key: str) -> Optional[str]:
    if not _redis_client:
        return None

    try:
        value = await _redis_client.get(key)
        MEMORY_OPERATIONS.labels(operation="get", memory_type="short_term").inc()
        return value
    except Exception:
        logger.exception("cache_get_failed", key=key)
        return None


async def cache_delete(key: str) -> bool:
    if not _redis_client:
        return False

    try:
        await _redis_client.delete(key)
        MEMORY_OPERATIONS.labels(operation="delete", memory_type="short_term").inc()
        return True
    except Exception:
        logger.exception("cache_delete_failed", key=key)
        return False


async def store_graph_relation(
    user_id: str,
    subject: str,
    predicate: str,
    obj: str,
) -> bool:
    if not _neo4j_driver:
        return False

    try:
        query = """
        MERGE (s:Entity {name: $subject, user_id: $user_id})
        MERGE (o:Entity {name: $object, user_id: $user_id})
        MERGE (s)-[r:RELATION {type: $predicate}]->(o)
        SET r.updated_at = datetime()
        RETURN s, r, o
        """
        async with _neo4j_driver.session() as session:
            await session.run(
                query,
                subject=subject,
                predicate=predicate,
                object=obj,
                user_id=user_id,
            )
        MEMORY_OPERATIONS.labels(operation="add", memory_type="graph").inc()
        logger.info(
            "graph_relation_stored",
            user_id=user_id,
            subject=subject,
            predicate=predicate,
        )
        return True
    except Exception:
        logger.exception("graph_relation_store_failed", user_id=user_id)
        return False


async def query_graph_relations(
    user_id: str,
    entity: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if not _neo4j_driver:
        return []

    try:
        query = """
        MATCH (s:Entity {user_id: $user_id})-[r:RELATION]->(o:Entity {user_id: $user_id})
        WHERE s.name CONTAINS $entity OR o.name CONTAINS $entity
        RETURN s.name AS subject, r.type AS predicate, o.name AS object
        LIMIT $limit
        """
        async with _neo4j_driver.session() as session:
            result = await session.run(
                query,
                user_id=user_id,
                entity=entity,
                limit=limit,
            )
            records = [record.data() async for record in result]
        MEMORY_OPERATIONS.labels(operation="query", memory_type="graph").inc()
        return records
    except Exception:
        logger.exception("graph_query_failed", user_id=user_id)
        return []
