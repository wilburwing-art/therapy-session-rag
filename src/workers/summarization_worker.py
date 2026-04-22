"""Summarization worker: generates recaps in the background."""

import logging
import uuid
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import select

from src.core.config import Settings, get_settings
from src.core.database import get_session_factory
from src.models.db.session import Session as SessionModel
from src.models.db.user import User, UserRole
from src.services.email_service import EmailService, EmailServiceError
from src.services.summarization_service import (
    SummarizationService,
    SummarizationServiceError,
)
from src.services.webhook_dispatcher import WebhookDispatcher

logger = logging.getLogger(__name__)


def get_redis_connection(settings: Settings | None = None) -> Redis:  # type: ignore[type-arg]
    settings = settings or get_settings()
    return Redis.from_url(str(settings.redis_url))


def get_summarization_queue(
    settings: Settings | None = None,
    queue_name: str = "summarization",
) -> Queue:
    conn = get_redis_connection(settings)
    return Queue(queue_name, connection=conn)


async def process_summarization_job(session_id: str) -> dict[str, Any]:
    """Generate a recap for a session.

    Non-fatal to the pipeline: failures here are logged but do not
    regress the session status, since the transcript and embeddings
    are already usable without a recap.
    """
    session_uuid = uuid.UUID(session_id)
    logger.info("Starting summarization job for session %s", session_id)

    session_factory = get_session_factory()
    settings = get_settings()
    therapist_email: str | None = None
    therapist_name: str | None = None
    session_date_str: str | None = None
    organization_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None
    recap_id: uuid.UUID | None = None

    async with session_factory() as db_session:
        service = SummarizationService(db_session)
        try:
            recap = await service.generate_recap(session_uuid)
            recap_id = recap.id

            # Capture therapist contact before the transaction closes so we
            # can email after commit without holding the DB session open.
            lookup = await db_session.execute(
                select(SessionModel).where(SessionModel.id == session_uuid)
            )
            session_row = lookup.scalar_one_or_none()
            if session_row is not None:
                therapist_lookup = await db_session.execute(
                    select(User).where(
                        User.id == session_row.therapist_id,
                        User.role == UserRole.THERAPIST,
                    )
                )
                therapist = therapist_lookup.scalar_one_or_none()
                if therapist is not None:
                    therapist_email = therapist.email
                    therapist_name = therapist.full_name
                    organization_id = therapist.organization_id
                patient_id = session_row.patient_id
                session_date_str = session_row.session_date.strftime("%b %d, %Y")

            await db_session.commit()
        except SummarizationServiceError as exc:
            logger.error(
                "Summarization job failed for session %s: %s", session_id, exc
            )
            await db_session.rollback()
            return {
                "session_id": session_id,
                "status": "failed",
                "error": str(exc),
            }

    if therapist_email and session_date_str:
        try:
            email_service = EmailService(settings=settings)
            recap_url = f"{settings.web_app_url}/sessions/{session_id}"
            email_service.send_recap_ready(
                to_email=therapist_email,
                session_date=session_date_str,
                recap_url=recap_url,
            )
            logger.info(
                "Recap-ready email dispatched to %s for session %s (therapist=%s)",
                therapist_email,
                session_id,
                therapist_name,
            )
        except EmailServiceError as exc:
            logger.warning(
                "Recap email failed for session %s: %s", session_id, exc
            )

    # Dispatch session.completed + recap.ready webhooks after the recap
    # has been committed and the therapist email has been sent. We open
    # a fresh session here so webhook dispatch cannot hold an
    # in-flight transaction open on the summarization path.
    if organization_id is not None and recap_id is not None:
        async with session_factory() as webhook_session:
            try:
                dispatcher = WebhookDispatcher(webhook_session)
                await dispatcher.dispatch(
                    organization_id=organization_id,
                    event_type="session.completed",
                    data={
                        "session_id": session_id,
                        "patient_id": (
                            str(patient_id) if patient_id is not None else None
                        ),
                    },
                )
                await dispatcher.dispatch(
                    organization_id=organization_id,
                    event_type="recap.ready",
                    data={
                        "session_id": session_id,
                        "recap_id": str(recap_id),
                        "patient_id": (
                            str(patient_id) if patient_id is not None else None
                        ),
                    },
                )
                await webhook_session.commit()
            except Exception:
                logger.warning(
                    "Webhook dispatch failed for session %s",
                    session_id,
                    exc_info=True,
                )
                await webhook_session.rollback()

    logger.info("Summarization job completed for session %s", session_id)
    return {
        "session_id": session_id,
        "recap_id": str(recap.id),
        "risk_flag_count": len(recap.risk_flags),
        "status": "completed",
    }


def queue_summarization(
    session_id: uuid.UUID,
    settings: Settings | None = None,
    queue_name: str = "summarization",
) -> str:
    queue = get_summarization_queue(settings, queue_name)
    rq_job = queue.enqueue(
        "src.workers.summarization_worker.process_summarization_job_sync",
        str(session_id),
        job_timeout="10m",
        result_ttl=86400,
        failure_ttl=86400,
    )
    logger.info(
        "Queued summarization job for session %s as RQ job %s",
        session_id,
        rq_job.id,
    )
    return str(rq_job.id)


def process_summarization_job_sync(session_id: str) -> dict[str, Any]:
    import asyncio

    from src.core.database import init_database

    settings = get_settings()
    init_database(settings)
    return asyncio.run(process_summarization_job(session_id))
