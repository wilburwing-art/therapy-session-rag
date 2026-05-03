"""Helper for writing DATA_ACCESS audit events from read endpoints.

SOC 2 CC6.1 / HIPAA 45 CFR § 164.312(b) require an audit trail of who
viewed patient data and when. Read endpoints call :func:`log_data_access`
just before returning. Publication is best-effort: a DB hiccup should
not block the therapist from seeing the record they asked for.

Events are written with ``event_category=DATA_ACCESS`` so the operator
panel's audit view and the retention-purge job can filter on them
separately from user_action / system events.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from src.models.db.event import EventCategory
from src.services.event_service import EventPublisher

logger = logging.getLogger(__name__)


async def log_data_access(
    events: EventPublisher,
    actor_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    subject: str,
    event_name: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Publish a DATA_ACCESS audit event.

    Args:
        events: Event publisher dependency.
        actor_id: User id of the viewer (therapist or admin). ``None``
            when the viewer is a service or the caller is unauthenticated
            (shouldn't happen on gated routes but kept defensive).
        organization_id: Org scope of the record being viewed.
        subject: Free-form tag identifying the resource class, e.g.
            ``"session"``, ``"patient"``, ``"admin_org"``. Mirrored into
            ``properties.subject`` so downstream queries can filter
            without parsing the event name.
        event_name: Dotted event identifier — e.g.
            ``"session.transcript_viewed"``.
        properties: Extra structured payload. Merged with ``subject``.

    Failures are logged at warning level; the caller never sees them.
    """
    payload: dict[str, Any] = {"subject": subject}
    if properties:
        payload.update(properties)

    try:
        await events.publish(
            event_name=event_name,
            category=EventCategory.DATA_ACCESS,
            organization_id=organization_id,
            actor_id=actor_id,
            properties=payload,
        )
    except Exception:
        # EventPublisher.publish already swallows, but double-protect the
        # read path in case we ever swap in a stricter publisher.
        logger.warning("Failed to record DATA_ACCESS event %s", event_name, exc_info=True)
