"""Admin service.

Backs the operator panel. Everything here is cross-tenant — callers
must be admin-gated at the router layer (``src.core.admin_gate``) since
this service itself does not enforce role checks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.organization import Organization
from src.models.db.session import Session as SessionRecording
from src.models.db.session import SessionStatus
from src.models.db.user import User
from src.models.domain.organization import (
    AdminAuditEventItem,
    AdminAuditEventPage,
    OrganizationAdminDetail,
    OrganizationAdminView,
    OrganizationSessionCountsByStatus,
    OrganizationUserView,
)


class AdminService:
    """Cross-tenant administrative queries and mutations."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def list_organizations(self) -> list[OrganizationAdminView]:
        """Return every organization with rollup counts for the ops list."""
        user_count_subq = (
            select(
                User.organization_id.label("org_id"),
                func.count(User.id).label("user_count"),
            )
            .group_by(User.organization_id)
            .subquery()
        )
        session_count_subq = (
            select(
                SessionRecording.patient_id.label("patient_id"),
                User.organization_id.label("org_id"),
                func.count(SessionRecording.id).label("session_count"),
            )
            .join(User, User.id == SessionRecording.patient_id)
            .group_by(SessionRecording.patient_id, User.organization_id)
            .subquery()
        )
        org_session_totals = (
            select(
                session_count_subq.c.org_id.label("org_id"),
                func.sum(session_count_subq.c.session_count).label("session_count"),
            )
            .group_by(session_count_subq.c.org_id)
            .subquery()
        )

        stmt = (
            select(
                Organization,
                func.coalesce(user_count_subq.c.user_count, 0).label("user_count"),
                func.coalesce(org_session_totals.c.session_count, 0).label("session_count"),
            )
            .select_from(Organization)
            .outerjoin(user_count_subq, user_count_subq.c.org_id == Organization.id)
            .outerjoin(
                org_session_totals,
                org_session_totals.c.org_id == Organization.id,
            )
            .order_by(Organization.created_at.desc())
        )
        result = await self.db_session.execute(stmt)
        rows = result.all()

        return [
            OrganizationAdminView(
                id=org.id,
                name=org.name,
                created_at=org.created_at,
                subscription_status=org.subscription_status.value,
                disabled_at=org.disabled_at,
                user_count=int(user_count or 0),
                session_count=int(session_count or 0),
            )
            for org, user_count, session_count in rows
        ]

    async def get_organization_detail(self, org_id: uuid.UUID) -> OrganizationAdminDetail:
        """Return the full admin detail view for one organization."""
        org_result = await self.db_session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if org is None:
            raise NotFoundError(resource="Organization", resource_id=str(org_id))

        users_result = await self.db_session.execute(
            select(User).where(User.organization_id == org_id).order_by(User.created_at.asc())
        )
        users = list(users_result.scalars().all())

        status_rows = await self.db_session.execute(
            select(
                SessionRecording.status,
                func.count(SessionRecording.id),
            )
            .join(User, User.id == SessionRecording.patient_id)
            .where(User.organization_id == org_id)
            .group_by(SessionRecording.status)
        )
        counts = OrganizationSessionCountsByStatus()
        for status, count in status_rows.all():
            setattr(counts, status.value, int(count))

        return OrganizationAdminDetail(
            id=org.id,
            name=org.name,
            created_at=org.created_at,
            subscription_status=org.subscription_status.value,
            stripe_customer_id=org.stripe_customer_id,
            stripe_subscription_id=org.stripe_subscription_id,
            trial_ends_at=org.trial_ends_at,
            current_period_end=org.current_period_end,
            disabled_at=org.disabled_at,
            users=[
                OrganizationUserView(
                    id=u.id,
                    email=u.email,
                    role=u.role.value,
                    full_name=u.full_name,
                    created_at=u.created_at,
                    email_verified_at=u.email_verified_at,
                )
                for u in users
            ],
            session_counts=counts,
        )

    async def disable_organization(self, org_id: uuid.UUID) -> Organization:
        """Suspend an organization. Idempotent — existing disabled_at is left
        in place so the original suspension timestamp is preserved.
        """
        org = await self._get_org_or_404(org_id)
        if org.disabled_at is None:
            org.disabled_at = datetime.now(UTC)
            await self.db_session.flush()
        return org

    async def enable_organization(self, org_id: uuid.UUID) -> Organization:
        """Clear the suspension flag. Idempotent."""
        org = await self._get_org_or_404(org_id)
        if org.disabled_at is not None:
            org.disabled_at = None
            await self.db_session.flush()
        return org

    async def list_audit_events(
        self,
        category: EventCategory | None = None,
        actor_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: datetime | None = None,
        limit: int = 50,
    ) -> AdminAuditEventPage:
        """Paginated, cross-tenant audit log.

        ``cursor`` is the ``event_timestamp`` of the previous page's last
        item. We fetch ``limit + 1`` rows to know whether more exist.
        """
        conditions: list[Any] = []
        if category is not None:
            conditions.append(AnalyticsEvent.event_category == category)
        if actor_id is not None:
            conditions.append(AnalyticsEvent.actor_id == actor_id)
        if since is not None:
            conditions.append(AnalyticsEvent.event_timestamp >= since)
        if until is not None:
            conditions.append(AnalyticsEvent.event_timestamp <= until)
        if cursor is not None:
            conditions.append(AnalyticsEvent.event_timestamp < cursor)

        stmt = select(AnalyticsEvent)
        for cond in conditions:
            stmt = stmt.where(cond)
        stmt = stmt.order_by(AnalyticsEvent.event_timestamp.desc()).limit(limit + 1)

        rows = list((await self.db_session.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            AdminAuditEventItem(
                id=e.id,
                event_name=e.event_name,
                event_category=e.event_category.value,
                organization_id=e.organization_id,
                actor_id=e.actor_id,
                session_id=e.session_id,
                event_timestamp=e.event_timestamp,
                properties=e.properties,
            )
            for e in page_rows
        ]
        next_cursor = page_rows[-1].event_timestamp.isoformat() if has_more and page_rows else None
        return AdminAuditEventPage(
            events=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def _get_org_or_404(self, org_id: uuid.UUID) -> Organization:
        result = await self.db_session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            raise NotFoundError(resource="Organization", resource_id=str(org_id))
        return org


# Make SessionStatus visible to anything importing from this module alongside
# the service (the admin frontend won't reach in here, but test helpers can).
__all__ = ["AdminService", "SessionStatus"]
