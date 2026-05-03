"""Unit tests for AdminService.

AdminService is thin — it delegates SQL to SQLAlchemy — so these tests
exercise the control flow (idempotency, 404s, result shaping) with a
mocked session. No Postgres needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError
from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.organization import Organization, SubscriptionStatus
from src.models.db.session import SessionStatus
from src.services.admin_service import AdminService


def _mock_org(
    org_id: uuid.UUID | None = None,
    name: str = "Acme Therapy",
    disabled_at: datetime | None = None,
    subscription_status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> MagicMock:
    org = MagicMock(spec=Organization)
    org.id = org_id or uuid.uuid4()
    org.name = name
    org.created_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    org.subscription_status = subscription_status
    org.disabled_at = disabled_at
    org.stripe_customer_id = "cus_123"
    org.stripe_subscription_id = "sub_456"
    org.trial_ends_at = None
    org.current_period_end = None
    return org


def _scalar_one_or_none(value: object) -> MagicMock:
    """Build a MagicMock that answers .scalar_one_or_none() -> value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(items: list[object]) -> MagicMock:
    """Build a MagicMock that answers .scalars().all() -> items."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _all(rows: list[tuple[object, ...]]) -> MagicMock:
    """Build a MagicMock that answers .all() -> rows."""
    result = MagicMock()
    result.all.return_value = rows
    return result


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> AdminService:
    return AdminService(mock_session)


class TestListOrganizations:
    async def test_list_returns_all_with_counts(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        org_a = _mock_org(name="Alpha")
        org_b = _mock_org(
            name="Beta",
            disabled_at=datetime(2026, 4, 10, tzinfo=UTC),
            subscription_status=SubscriptionStatus.CANCELED,
        )
        mock_session.execute.return_value = _all([(org_a, 4, 12), (org_b, 2, 0)])

        result = await service.list_organizations()

        assert len(result) == 2
        assert result[0].name == "Alpha"
        assert result[0].user_count == 4
        assert result[0].session_count == 12
        assert result[0].disabled_at is None
        assert result[0].subscription_status == "active"
        assert result[1].name == "Beta"
        assert result[1].disabled_at is not None
        assert result[1].subscription_status == "canceled"
        assert result[1].user_count == 2

    async def test_list_handles_null_counts(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        """Orgs with no users/sessions still show up with zeros."""
        org = _mock_org(name="Empty Practice")
        mock_session.execute.return_value = _all([(org, None, None)])

        result = await service.list_organizations()

        assert len(result) == 1
        assert result[0].user_count == 0
        assert result[0].session_count == 0


class TestGetOrganizationDetail:
    async def test_detail_success(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        org = _mock_org()

        # three execute() calls: fetch org, fetch users, fetch status counts
        user_one = MagicMock()
        user_one.id = uuid.uuid4()
        user_one.email = "doc@example.com"
        user_one.role = MagicMock()
        user_one.role.value = "therapist"
        user_one.full_name = "Dr. Doc"
        user_one.created_at = datetime(2026, 1, 16, tzinfo=UTC)
        user_one.email_verified_at = datetime(2026, 1, 17, tzinfo=UTC)

        mock_session.execute.side_effect = [
            _scalar_one_or_none(org),
            _scalars_all([user_one]),
            _all(
                [
                    (SessionStatus.READY, 5),
                    (SessionStatus.FAILED, 1),
                ]
            ),
        ]

        detail = await service.get_organization_detail(org.id)

        assert detail.id == org.id
        assert detail.name == "Acme Therapy"
        assert len(detail.users) == 1
        assert detail.users[0].email == "doc@example.com"
        assert detail.users[0].role == "therapist"
        assert detail.session_counts.ready == 5
        assert detail.session_counts.failed == 1
        assert detail.session_counts.pending == 0

    async def test_detail_missing_org_raises_not_found(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.return_value = _scalar_one_or_none(None)

        with pytest.raises(NotFoundError):
            await service.get_organization_detail(uuid.uuid4())


class TestDisableEnableOrganization:
    async def test_disable_sets_disabled_at(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        org = _mock_org()
        mock_session.execute.return_value = _scalar_one_or_none(org)

        before = datetime.now(UTC)
        result = await service.disable_organization(org.id)
        after = datetime.now(UTC)

        assert result.disabled_at is not None
        assert before - timedelta(seconds=1) <= result.disabled_at <= after + timedelta(seconds=1)
        mock_session.flush.assert_awaited_once()

    async def test_disable_is_idempotent(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        """Re-disabling an already-disabled org preserves the original stamp."""
        original_stamp = datetime(2026, 3, 1, tzinfo=UTC)
        org = _mock_org(disabled_at=original_stamp)
        mock_session.execute.return_value = _scalar_one_or_none(org)

        result = await service.disable_organization(org.id)

        assert result.disabled_at == original_stamp
        mock_session.flush.assert_not_awaited()

    async def test_enable_clears_disabled_at(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        org = _mock_org(disabled_at=datetime(2026, 3, 1, tzinfo=UTC))
        mock_session.execute.return_value = _scalar_one_or_none(org)

        result = await service.enable_organization(org.id)

        assert result.disabled_at is None
        mock_session.flush.assert_awaited_once()

    async def test_enable_already_active_is_noop(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        org = _mock_org(disabled_at=None)
        mock_session.execute.return_value = _scalar_one_or_none(org)

        result = await service.enable_organization(org.id)

        assert result.disabled_at is None
        mock_session.flush.assert_not_awaited()

    async def test_disable_missing_org_raises(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.return_value = _scalar_one_or_none(None)

        with pytest.raises(NotFoundError):
            await service.disable_organization(uuid.uuid4())


class TestListAuditEvents:
    async def test_pagination_marks_has_more(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        """Returns limit rows and flags has_more=True if an extra was fetched."""
        limit = 2
        rows: list[AnalyticsEvent] = []
        base_time = datetime(2026, 4, 20, 12, 0, 0, tzinfo=UTC)
        for i in range(limit + 1):
            ev = MagicMock(spec=AnalyticsEvent)
            ev.id = uuid.uuid4()
            ev.event_name = f"evt_{i}"
            ev.event_category = MagicMock()
            ev.event_category.value = "user_action"
            ev.organization_id = uuid.uuid4()
            ev.actor_id = None
            ev.session_id = None
            ev.event_timestamp = base_time - timedelta(minutes=i)
            ev.properties = {"i": i}
            rows.append(ev)

        mock_session.execute.return_value = _scalars_all(rows)

        page = await service.list_audit_events(limit=limit)

        assert page.has_more is True
        assert len(page.events) == limit
        assert page.next_cursor is not None
        assert page.events[0].event_name == "evt_0"
        assert page.events[1].event_name == "evt_1"

    async def test_no_more_pages_returns_null_cursor(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        ev = MagicMock(spec=AnalyticsEvent)
        ev.id = uuid.uuid4()
        ev.event_name = "lone_event"
        ev.event_category = MagicMock()
        ev.event_category.value = "system"
        ev.organization_id = uuid.uuid4()
        ev.actor_id = None
        ev.session_id = None
        ev.event_timestamp = datetime.now(UTC)
        ev.properties = None

        mock_session.execute.return_value = _scalars_all([ev])

        page = await service.list_audit_events(limit=10)

        assert page.has_more is False
        assert page.next_cursor is None
        assert len(page.events) == 1

    async def test_filters_are_applied(
        self,
        service: AdminService,
        mock_session: AsyncMock,
    ) -> None:
        """Smoke-test: when filters are passed, the service runs without error
        and returns an empty page if nothing matches."""
        mock_session.execute.return_value = _scalars_all([])

        actor = uuid.uuid4()
        page = await service.list_audit_events(
            category=EventCategory.SYSTEM,
            actor_id=actor,
            since=datetime(2026, 4, 1, tzinfo=UTC),
            until=datetime(2026, 4, 30, tzinfo=UTC),
            cursor=datetime(2026, 4, 15, tzinfo=UTC),
            limit=5,
        )

        assert page.events == []
        assert page.has_more is False
        assert page.next_cursor is None
