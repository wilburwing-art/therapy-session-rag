"""Unit tests for admin API endpoints.

The admin router is role-gated by ``require_admin``. These tests swap
the service layer out via FastAPI dependency overrides so Postgres
isn't required, then verify:

1. An authenticated admin can hit the endpoints and receives well-shaped
   bodies.
2. A non-admin therapist is rejected with 403.
3. An unauthenticated caller is rejected with 401.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.admin import get_admin_service, router
from src.core.admin_gate import require_admin
from src.core.database import get_db_session
from src.core.exceptions import ForbiddenError, UnauthorizedError, setup_exception_handlers
from src.models.db.user import User, UserRole
from src.models.domain.organization import (
    AdminAuditEventItem,
    AdminAuditEventPage,
    OrganizationAdminDetail,
    OrganizationAdminView,
    OrganizationSessionCountsByStatus,
    OrganizationUserView,
)


def _admin_user() -> MagicMock:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.organization_id = uuid.uuid4()
    u.email = "admin@platform.io"
    u.full_name = "Platform Admin"
    u.role = UserRole.ADMIN
    u.email_verified_at = datetime(2026, 1, 1, tzinfo=UTC)
    u.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    u.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return u


def _make_org_view(name: str = "Acme") -> OrganizationAdminView:
    return OrganizationAdminView(
        id=uuid.uuid4(),
        name=name,
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
        subscription_status="active",
        disabled_at=None,
        user_count=3,
        session_count=11,
    )


def _make_org_detail(org_id: uuid.UUID, name: str = "Acme") -> OrganizationAdminDetail:
    return OrganizationAdminDetail(
        id=org_id,
        name=name,
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
        subscription_status="active",
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
        trial_ends_at=None,
        current_period_end=None,
        disabled_at=None,
        users=[
            OrganizationUserView(
                id=uuid.uuid4(),
                email="doc@example.com",
                role="therapist",
                full_name="Dr. Doc",
                created_at=datetime(2026, 1, 16, tzinfo=UTC),
                email_verified_at=datetime(2026, 1, 17, tzinfo=UTC),
            ),
        ],
        session_counts=OrganizationSessionCountsByStatus(ready=4, failed=1),
    )


@pytest.fixture
def admin() -> MagicMock:
    return _admin_user()


@pytest.fixture
def mock_admin_service() -> MagicMock:
    svc = MagicMock()
    svc.list_organizations = AsyncMock()
    svc.get_organization_detail = AsyncMock()
    svc.disable_organization = AsyncMock()
    svc.enable_organization = AsyncMock()
    svc.list_audit_events = AsyncMock()
    return svc


@pytest.fixture
def app(mock_admin_service: MagicMock, admin: MagicMock) -> FastAPI:
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/admin")

    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    test_app.dependency_overrides[require_admin] = lambda: admin
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestListOrganizations:
    def test_list_orgs_returns_rows(
        self,
        client: TestClient,
        mock_admin_service: MagicMock,
    ) -> None:
        mock_admin_service.list_organizations.return_value = [
            _make_org_view("Alpha"),
            _make_org_view("Beta"),
        ]

        response = client.get("/admin/orgs")

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert {r["name"] for r in body} == {"Alpha", "Beta"}
        for row in body:
            assert row["user_count"] == 3
            assert row["session_count"] == 11
        mock_admin_service.list_organizations.assert_awaited_once()


class TestGetOrganizationDetail:
    def test_detail_returns_users_and_counts(
        self,
        client: TestClient,
        mock_admin_service: MagicMock,
    ) -> None:
        org_id = uuid.uuid4()
        mock_admin_service.get_organization_detail.return_value = _make_org_detail(org_id)

        response = client.get(f"/admin/orgs/{org_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(org_id)
        assert len(body["users"]) == 1
        assert body["users"][0]["role"] == "therapist"
        assert body["session_counts"]["ready"] == 4
        assert body["session_counts"]["failed"] == 1


class TestDisableEnableOrganization:
    def test_disable_returns_updated_detail(
        self,
        client: TestClient,
        mock_admin_service: MagicMock,
    ) -> None:
        org_id = uuid.uuid4()
        detail = _make_org_detail(org_id)
        detail.disabled_at = datetime(2026, 4, 21, 10, 0, tzinfo=UTC)
        mock_admin_service.disable_organization.return_value = MagicMock()
        mock_admin_service.get_organization_detail.return_value = detail

        response = client.post(f"/admin/orgs/{org_id}/disable")

        assert response.status_code == 200
        body = response.json()
        assert body["disabled_at"] is not None
        mock_admin_service.disable_organization.assert_awaited_once()

    def test_enable_returns_updated_detail(
        self,
        client: TestClient,
        mock_admin_service: MagicMock,
    ) -> None:
        org_id = uuid.uuid4()
        detail = _make_org_detail(org_id)
        mock_admin_service.enable_organization.return_value = MagicMock()
        mock_admin_service.get_organization_detail.return_value = detail

        response = client.post(f"/admin/orgs/{org_id}/enable")

        assert response.status_code == 200
        body = response.json()
        assert body["disabled_at"] is None
        mock_admin_service.enable_organization.assert_awaited_once()


class TestListAuditEvents:
    def test_events_endpoint_returns_page(
        self,
        client: TestClient,
        mock_admin_service: MagicMock,
    ) -> None:
        mock_admin_service.list_audit_events.return_value = AdminAuditEventPage(
            events=[
                AdminAuditEventItem(
                    id=uuid.uuid4(),
                    event_name="patient.data_exported",
                    event_category="system",
                    organization_id=uuid.uuid4(),
                    actor_id=uuid.uuid4(),
                    session_id=None,
                    event_timestamp=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
                    properties={"patient_id": str(uuid.uuid4())},
                ),
            ],
            next_cursor=None,
            has_more=False,
        )

        response = client.get("/admin/events?category=system&limit=10")

        assert response.status_code == 200
        body = response.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["event_name"] == "patient.data_exported"
        assert body["has_more"] is False
        assert body["next_cursor"] is None
        mock_admin_service.list_audit_events.assert_awaited_once()

    def test_events_filter_params_forwarded(
        self,
        client: TestClient,
        mock_admin_service: MagicMock,
    ) -> None:
        mock_admin_service.list_audit_events.return_value = AdminAuditEventPage(
            events=[],
            next_cursor=None,
            has_more=False,
        )

        actor = uuid.uuid4()
        response = client.get(
            "/admin/events",
            params={
                "category": "user_action",
                "actor_id": str(actor),
                "since": "2026-04-01T00:00:00Z",
                "until": "2026-04-30T00:00:00Z",
                "limit": 20,
            },
        )

        assert response.status_code == 200
        _, kwargs = mock_admin_service.list_audit_events.call_args
        assert str(kwargs["actor_id"]) == str(actor)
        assert kwargs["limit"] == 20


class TestAdminRoleGating:
    def test_non_admin_gets_403(
        self,
        app: FastAPI,
        mock_admin_service: MagicMock,
    ) -> None:
        def _deny() -> None:
            raise ForbiddenError("Admin privileges required")

        app.dependency_overrides[require_admin] = _deny
        local_client = TestClient(app)

        response = local_client.get("/admin/orgs")

        assert response.status_code == 403
        mock_admin_service.list_organizations.assert_not_called()

    def test_unauthenticated_gets_401(
        self,
        app: FastAPI,
        mock_admin_service: MagicMock,
    ) -> None:
        def _unauth() -> None:
            raise UnauthorizedError("Admin session required")

        app.dependency_overrides[require_admin] = _unauth
        local_client = TestClient(app)

        response = local_client.get("/admin/orgs")

        assert response.status_code == 401
        mock_admin_service.list_organizations.assert_not_called()
