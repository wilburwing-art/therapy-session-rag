"""Tests for User model and schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.db.user import User, UserRole
from src.models.domain.user import UserCreate, UserRead
from src.models.domain.user import UserRole as DomainUserRole


class TestUserRole:
    """Tests for UserRole enum."""

    def test_role_values(self) -> None:
        """Test UserRole has correct values."""
        assert UserRole.THERAPIST.value == "therapist"
        assert UserRole.PATIENT.value == "patient"
        assert UserRole.ADMIN.value == "admin"

    def test_role_is_string_enum(self) -> None:
        """Test UserRole is a string enum."""
        assert isinstance(UserRole.THERAPIST, str)
        assert UserRole.THERAPIST.value == "therapist"


class TestUserModel:
    """Tests for User database model."""

    def test_user_creation(self) -> None:
        """Test User model can be instantiated."""
        org_id = uuid.uuid4()
        user = User(
            organization_id=org_id,
            email="test@example.com",
            role=UserRole.THERAPIST,
        )

        assert user.email == "test@example.com"
        assert user.role == UserRole.THERAPIST
        assert user.organization_id == org_id

    def test_user_has_uuid_id(self) -> None:
        """Test User model has UUID primary key."""
        id_type = User.__table__.c.id.type
        assert id_type.__class__.__name__ == "UUID"

    def test_user_tablename(self) -> None:
        """Test User model has correct table name."""
        assert User.__tablename__ == "users"

    def test_user_has_organization_fk(self) -> None:
        """Test User model has foreign key to organization."""
        org_id_col = User.__table__.c.organization_id
        fk = list(org_id_col.foreign_keys)[0]
        assert fk.column.table.name == "organizations"


class TestUserCreate:
    """Tests for UserCreate schema."""

    def test_create_with_valid_data(self) -> None:
        """Test UserCreate with valid data."""
        org_id = uuid.uuid4()
        schema = UserCreate(
            email="test@example.com",
            role=DomainUserRole.THERAPIST,
            organization_id=org_id,
        )

        assert schema.email == "test@example.com"
        assert schema.role == DomainUserRole.THERAPIST
        assert schema.organization_id == org_id

    def test_create_requires_email(self) -> None:
        """Test UserCreate requires email field."""
        with pytest.raises(ValidationError):
            UserCreate(
                role=DomainUserRole.THERAPIST,
                organization_id=uuid.uuid4(),
            )  # type: ignore[call-arg]

    def test_create_validates_email_format(self) -> None:
        """Test UserCreate validates email format."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="not-an-email",
                role=DomainUserRole.THERAPIST,
                organization_id=uuid.uuid4(),
            )

    def test_create_requires_role(self) -> None:
        """Test UserCreate requires role field."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                organization_id=uuid.uuid4(),
            )  # type: ignore[call-arg]

    def test_create_validates_role(self) -> None:
        """Test UserCreate validates role value."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                role="invalid_role",  # type: ignore[arg-type]
                organization_id=uuid.uuid4(),
            )


class TestUserRead:
    """Tests for UserRead schema."""

    def test_read_from_dict(self) -> None:
        """Test UserRead can be created from dict."""
        now = datetime.now(UTC)
        org_id = uuid.uuid4()
        data = {
            "id": uuid.uuid4(),
            "email": "test@example.com",
            "role": DomainUserRole.PATIENT,
            "organization_id": org_id,
            "created_at": now,
            "updated_at": now,
        }

        schema = UserRead.model_validate(data)

        assert schema.email == "test@example.com"
        assert schema.role == DomainUserRole.PATIENT

    def test_read_from_orm(self) -> None:
        """Test UserRead can be created from ORM object."""

        class FakeORM:
            id = uuid.uuid4()
            email = "test@example.com"
            role = DomainUserRole.ADMIN
            organization_id = uuid.uuid4()
            created_at = datetime.now(UTC)
            updated_at = datetime.now(UTC)

        schema = UserRead.model_validate(FakeORM())

        assert schema.email == "test@example.com"
        assert schema.role == DomainUserRole.ADMIN
