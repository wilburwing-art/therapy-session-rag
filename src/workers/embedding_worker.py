"""Embedding worker for processing embedding jobs."""

import logging
import uuid
from typing import Any

from redis import Redis
from rq import Queue

from src.core.config import Settings, get_settings
from src.core.database import get_session_factory
from src.services.embedding_service import EmbeddingService, EmbeddingServiceError

logger = logging.getLogger(__name__)


def get_redis_connection(settings: Settings | None = None) -> Redis:  # type: ignore[type-arg]
    """Get Redis connection.

    Args:
        settings: Application settings

    Returns:
        Redis connection
    """
    settings = settings or get_settings()
    return Redis.from_url(str(settings.redis_url))


def get_embedding_queue(
    settings: Settings | None = None,
    queue_name: str = "embedding",
) -> Queue:
    """Get the embedding job queue.

    Args:
        settings: Application settings
        queue_name: Name of the queue

    Returns:
        RQ Queue instance
    """
    conn = get_redis_connection(settings)
    return Queue(queue_name, connection=conn)


async def process_embedding_job(session_id: str) -> dict[str, Any]:
    """Process an embedding job.

    This is the main worker function that processes embedding jobs
    from the queue.

    Args:
        session_id: UUID string of the session to process

    Returns:
        Dict with job result information

    Raises:
        EmbeddingServiceError: If processing fails
    """
    session_uuid = uuid.UUID(session_id)
    logger.info(f"Starting embedding job for session: {session_id}")

    try:
        # Get database session
        session_factory = get_session_factory()
        async with session_factory() as db_session:
            service = EmbeddingService(db_session)

            # Process the embeddings
            chunks = await service.process_embeddings(session_uuid)

            # Commit the transaction
            await db_session.commit()

            logger.info(
                f"Embedding job completed for session {session_id}: "
                f"{len(chunks)} chunks created"
            )

            # Return result for downstream processing
            return {
                "session_id": session_id,
                "chunk_count": len(chunks),
                "status": "completed",
            }

    except EmbeddingServiceError as e:
        logger.error(f"Embedding job failed for session {session_id}: {e}")
        raise

    except Exception as e:
        logger.exception(f"Unexpected error processing embedding job {session_id}: {e}")
        raise EmbeddingServiceError(f"Unexpected error: {e}") from e


def queue_embedding(
    session_id: uuid.UUID,
    settings: Settings | None = None,
    queue_name: str = "embedding",
) -> str:
    """Queue an embedding job for processing.

    Args:
        session_id: The session UUID
        settings: Application settings
        queue_name: Name of the queue

    Returns:
        RQ job ID
    """
    queue = get_embedding_queue(settings, queue_name)

    rq_job = queue.enqueue(
        "src.workers.embedding_worker.process_embedding_job_sync",
        str(session_id),
        job_timeout="15m",  # Embedding can take time for long transcripts
        result_ttl=86400,  # Keep result for 24 hours
        failure_ttl=86400,  # Keep failed job info for 24 hours
    )

    logger.info(f"Queued embedding job for session {session_id} as RQ job {rq_job.id}")

    return str(rq_job.id)


def process_embedding_job_sync(session_id: str) -> dict[str, Any]:
    """Synchronous wrapper for process_embedding_job.

    RQ doesn't natively support async functions, so this wrapper
    runs the async function in an event loop.

    Args:
        session_id: UUID string of the session

    Returns:
        Dict with job result information
    """
    import asyncio

    return asyncio.run(process_embedding_job(session_id))
