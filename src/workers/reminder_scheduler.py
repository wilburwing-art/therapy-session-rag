"""Reminder scheduler.

Uses rq-scheduler to run a recurring job that scans the reminders_sent
audit table for due reminders and enqueues them for delivery. The
scheduler lifecycle is wired from :mod:`src.main` on app startup.

Design notes:
- The scheduler object is process-global (one per API process). We
  register a single recurring tick; the tick itself fans out to
  per-patient send jobs so a slow Twilio call can't stall other work.
- If ``settings.reminders_enabled`` is false the module exposes no-op
  functions so tests and local dev don't need Redis or rq-scheduler
  running.
- All "what reminders are due" logic lives in a separate service
  module (deferred, out of scope for this change). This module is only
  responsible for scheduling the tick.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from redis import Redis

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_REMINDER_QUEUE_NAME = "reminders"
_TICK_JOB_ID = "reminders.tick"


def _redis(settings: Settings) -> Redis:  # type: ignore[type-arg]
    return Redis.from_url(str(settings.redis_url))


def reminder_tick() -> dict[str, Any]:
    """Recurring tick fired by rq-scheduler.

    For now this is an intentionally minimal hook: it logs that it ran
    and returns a status dict. The reminder-dispatch service will
    replace the body once homework deadlines and session times are
    queryable through their own repositories.
    """
    tick_id = str(uuid.uuid4())
    logger.info("reminder_tick.start", extra={"tick_id": tick_id})
    # TODO: dispatch due reminders. Left as a stub until the dispatcher
    #       service lands, so the scheduler plumbing can be reviewed
    #       independently.
    return {"tick_id": tick_id, "status": "noop"}


def start_scheduler(settings: Settings | None = None) -> bool:
    """Register the recurring reminder tick with rq-scheduler.

    Returns:
        True when a schedule was registered, False when reminders are
        disabled or rq-scheduler isn't available. The caller should log
        but not raise on False.
    """
    settings = settings or get_settings()
    if not settings.reminders_enabled:
        logger.info("reminder_scheduler.disabled")
        return False

    try:
        from rq_scheduler import Scheduler
    except ImportError:
        logger.warning("reminder_scheduler.rq_scheduler_missing")
        return False

    conn = _redis(settings)
    scheduler = Scheduler(queue_name=_REMINDER_QUEUE_NAME, connection=conn)

    # Idempotent: cancel any previous registration with the same id
    # before scheduling to avoid duplicate ticks when the app restarts.
    for job in scheduler.get_jobs():
        if job.id == _TICK_JOB_ID:
            scheduler.cancel(job)

    scheduler.schedule(
        scheduled_time=__now_utc(),
        func="src.workers.reminder_scheduler.reminder_tick",
        id=_TICK_JOB_ID,
        interval=settings.reminders_scheduler_interval_seconds,
        repeat=None,
        result_ttl=3600,
    )
    logger.info(
        "reminder_scheduler.registered",
        extra={
            "interval_s": settings.reminders_scheduler_interval_seconds,
            "queue": _REMINDER_QUEUE_NAME,
        },
    )
    return True


def stop_scheduler(settings: Settings | None = None) -> None:
    """Cancel the recurring tick. Safe to call when the scheduler
    was never started."""
    settings = settings or get_settings()
    if not settings.reminders_enabled:
        return
    try:
        from rq_scheduler import Scheduler
    except ImportError:
        return

    conn = _redis(settings)
    scheduler = Scheduler(queue_name=_REMINDER_QUEUE_NAME, connection=conn)
    for job in scheduler.get_jobs():
        if job.id == _TICK_JOB_ID:
            scheduler.cancel(job)
    logger.info("reminder_scheduler.stopped")


def __now_utc() -> Any:
    """Timezone-aware current time. Kept tiny and local so tests can
    monkey-patch this module without pulling in a full clock
    abstraction."""
    from datetime import UTC, datetime

    return datetime.now(UTC)


__all__ = [
    "reminder_tick",
    "start_scheduler",
    "stop_scheduler",
]
