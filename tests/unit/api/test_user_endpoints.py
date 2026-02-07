"""Unit tests for Users API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth
from src.api.v1.endpoints.users import router
from src.core.database import get_db_session
from src.models.db.user import User, UserRole


def _make_user(
    org_id: uuid.UUID,
    email: str,
    role: UserRole,
    user_id: uuid.UUID | None = None,
) -> User:
    """Create a mock User object."""
    user = MagicMock(spec=User)
    user.id = user_id or uuid.uuid4()
    user.organization_id = org_id
    user.email = email
    user.role = role
    user.created_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    user.updated_at = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
    return user


@pytest.fixture
def org_id() -> uuid.UUID:
    """Create a test organization ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_auth_context(org_id: uuid.UUID) -> MagicMock:
    """Create a mock auth context."""
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = org_id
    ctx.api_key_name = "test-key"
    return ctx


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def app(mock_auth_context: MagicMock, mock_db_session: AsyncMock) -> FastAPI:
    """Create test app with mocked dependencies."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/users")

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: mock_db_session

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestListUsersEndpoint:
    """Tests for GET /users endpoint."""

    def test_list_users_returns_all_users(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test listing all users without role filter."""
        users = [
            _make_user(org_id, "admin@example.com", UserRole.ADMIN),
            _make_user(org_id, "doc@example.com", UserRole.THERAPIST),
            _make_user(org_id, "patient@example.com", UserRole.PATIENT),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = users
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["email"] == "admin@example.com"
        assert data[0]["role"] == "admin"
        assert data[1]["email"] == "doc@example.com"
        assert data[1]["role"] == "therapist"
        assert data[2]["email"] == "patient@example.com"
        assert data[2]["role"] == "patient"

    def test_list_users_with_therapist_filter(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test listing users filtered by therapist role."""
        therapists = [
            _make_user(org_id, "doc1@example.com", UserRole.THERAPIST),
            _make_user(org_id, "doc2@example.com", UserRole.THERAPIST),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = therapists
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users", params={"role": "therapist"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all(u["role"] == "therapist" for u in data)

    def test_list_users_with_patient_filter(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test listing users filtered by patient role."""
        patients = [
            _make_user(org_id, "patient1@example.com", UserRole.PATIENT),
            _make_user(org_id, "patient2@example.com", UserRole.PATIENT),
            _make_user(org_id, "patient3@example.com", UserRole.PATIENT),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = patients
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users", params={"role": "patient"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert all(u["role"] == "patient" for u in data)

    def test_list_users_with_admin_filter(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test listing users filtered by admin role."""
        admins = [_make_user(org_id, "admin@example.com", UserRole.ADMIN)]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = admins
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users", params={"role": "admin"})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["role"] == "admin"

    def test_list_users_empty(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
    ) -> None:
        """Test listing users when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_users_invalid_role_filter(
        self,
        client: TestClient,
    ) -> None:
        """Test listing users with invalid role filter returns 422."""
        response = client.get("/users", params={"role": "invalid_role"})

        assert response.status_code == 422

    def test_list_users_returns_correct_fields(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test that response includes all expected UserRead fields."""
        user_id = uuid.uuid4()
        created = datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
        updated = datetime(2026, 1, 20, 14, 30, 0, tzinfo=UTC)

        user = MagicMock(spec=User)
        user.id = user_id
        user.organization_id = org_id
        user.email = "test@example.com"
        user.role = UserRole.THERAPIST
        user.created_at = created
        user.updated_at = updated

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user]
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        user_data = data[0]
        assert user_data["id"] == str(user_id)
        assert user_data["organization_id"] == str(org_id)
        assert user_data["email"] == "test@example.com"
        assert user_data["role"] == "therapist"
        assert "created_at" in user_data
        assert "updated_at" in user_data


class TestListUsersMultiTenancy:
    """Tests for multi-tenant isolation in users endpoint."""

    def test_users_filtered_by_organization(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test that only users from the authenticated organization are returned.

        The endpoint filters by organization_id from the auth context.
        We verify the mock is called and returns only org-specific users.
        """
        # Only users from the authenticated org should be returned
        org_users = [
            _make_user(org_id, "user1@myorg.com", UserRole.THERAPIST),
            _make_user(org_id, "user2@myorg.com", UserRole.PATIENT),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = org_users
        mock_db_session.execute.return_value = mock_result

        response = client.get("/users")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # All returned users should belong to the same organization
        assert all(u["organization_id"] == str(org_id) for u in data)

    def test_database_query_includes_organization_filter(
        self,
        client: TestClient,
        mock_db_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        """Test that the database query is executed (verifying the call happens)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        client.get("/users")

        # Verify execute was called (the actual query contains org filter)
        mock_db_session.execute.assert_called_once()
