"""Transcription worker for processing transcription jobs."""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import select

from src.core.config import Settings, get_settings
from src.core.database import get_session_factory
from src.models.db.session import Session as SessionModel
from src.models.db.user import User
from src.services.billing_service import BillingService, BillingServiceError
from src.services.transcription_service import TranscriptionError, TranscriptionService

logger = logging.getLogger(__name__)

# Telemetry is opt-in — guard the import so a missing/broken OTEL install
# never breaks the transcription worker. Falls back to a no-op context manager.
try:
    from src.core.telemetry import record_duration as _record_duration
except ImportError:  # pragma: no cover - defensive

    @contextmanager
    def _record_duration(
        operation: str,  # noqa: ARG001 - signature-compat no-op stub
        attributes: dict[str, str] | None = None,  # noqa: ARG001
    ) -> Iterator[None]:
        yield


def get_redis_connection(settings: Settings | None = None) -> Redis:  # type: ignore[type-arg]
    """Get Redis connection.

    Args:
        settings: Application settings

    Returns:
        Redis connection
    """
    settings = settings or get_settings()
    return Redis.from_url(str(settings.redis_url))


def get_transcription_queue(
    settings: Settings | None = None,
    queue_name: str = "transcription",
) -> Queue:
    """Get the transcription job queue.

    Args:
        settings: Application settings
        queue_name: Name of the queue

    Returns:
        RQ Queue instance
    """
    conn = get_redis_connection(settings)
    return Queue(queue_name, connection=conn)


async def process_transcription_job(job_id: str) -> dict[str, Any]:
    """Process a transcription job.

    This is the main worker function that processes transcription jobs
    from the queue.

    Args:
        job_id: UUID string of the transcription job

    Returns:
        Dict with job result information

    Raises:
        TranscriptionError: If processing fails
    """
    job_uuid = uuid.UUID(job_id)
    logger.info(f"Starting transcription job: {job_id}")

    try:
        # Get database session
        session_factory = get_session_factory()
        async with session_factory() as db_session:
            service = TranscriptionService(db_session)

            # Process the transcription
            with _record_duration("worker.transcription"):
                transcript = await service.process_transcription(job_uuid)

            # Commit the transaction
            await db_session.commit()

            logger.info(f"Transcription job completed: {job_id}")

            # Best-effort metered-billing increment: count one unit of
            # sessions_transcribed against the therapist's org for the
            # current billing period. Isolated in its own session so a
            # billing failure can't roll back the transcript.
            await _increment_transcription_usage(transcript.session_id)

            # Return result for downstream processing
            return {
                "job_id": job_id,
                "transcript_id": str(transcript.id),
                "session_id": str(transcript.session_id),
                "word_count": transcript.word_count,
                "status": "completed",
            }

    except TranscriptionError as e:
        logger.error(f"Transcription job failed: {job_id} - {e}")
        raise

    except Exception as e:
        logger.exception(f"Unexpected error processing job {job_id}: {e}")
        raise TranscriptionError(f"Unexpected error: {e}") from e


def queue_transcription(
    job_id: uuid.UUID,
    settings: Settings | None = None,
    queue_name: str = "transcription",
) -> str:
    """Queue a transcription job for processing.

    Args:
        job_id: The transcription job UUID
        settings: Application settings
        queue_name: Name of the queue

    Returns:
        RQ job ID
    """
    queue = get_transcription_queue(settings, queue_name)

    rq_job = queue.enqueue(
        "src.workers.transcription_worker.process_transcription_job_sync",
        str(job_id),
        job_timeout="30m",  # Long audio files may take time
        result_ttl=86400,  # Keep result for 24 hours
        failure_ttl=86400,  # Keep failed job info for 24 hours
    )

    logger.info(f"Queued transcription job {job_id} as RQ job {rq_job.id}")

    return str(rq_job.id)


def process_transcription_job_sync(job_id: str) -> dict[str, Any]:
    """Synchronous wrapper for process_transcription_job.

    RQ doesn't natively support async functions, so this wrapper
    runs the async function in an event loop.

    Args:
        job_id: UUID string of the transcription job

    Returns:
        Dict with job result information
    """
    import asyncio

    from src.core.database import init_database

    # Initialize database for this worker process
    settings = get_settings()
    init_database(settings)

    return asyncio.run(process_transcription_job(job_id))


async def _increment_transcription_usage(session_id: uuid.UUID) -> None:
    """Best-effort increment of BillingUsage.sessions_transcribed.

    Uses a short-lived session so it can commit (or fail) independently
    of the main transcription transaction. Never raises — a billing
    failure must not corrupt the transcript record.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as billing_db:
            stmt = (
                select(User.organization_id)
                .join(SessionModel, SessionModel.therapist_id == User.id)
                .where(SessionModel.id == session_id)
            )
            result = await billing_db.execute(stmt)
            org_id = result.scalar_one_or_none()
            if org_id is None:
                logger.warning(
                    "No organization for session %s; skipping usage increment",
                    session_id,
                )
                return
            service = BillingService(billing_db)
            await service.record_sessions_transcribed(org_id)
            await billing_db.commit()
    except BillingServiceError as exc:
        logger.warning(
            "Billing usage increment failed for session %s: %s",
            session_id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001 - isolate billing from worker
        logger.exception(
            "Unexpected error recording transcription usage for session %s: %s",
            session_id,
            exc,
        )
