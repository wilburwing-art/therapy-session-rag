"""Tests for Organization model and schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.db.organization import Organization
from src.models.domain.organization import OrganizationCreate, OrganizationRead


class TestOrganizationModel:
    """Tests for Organization database model."""

    def test_organization_creation(self) -> None:
        """Test Organization model can be instantiated."""
        org = Organization(name="Test Clinic")

        assert org.name == "Test Clinic"

    def test_organization_has_uuid_id(self) -> None:
        """Test Organization model has UUID primary key."""
        # Verify the column configuration
        id_type = Organization.__table__.c.id.type
        assert id_type.__class__.__name__ == "UUID"

    def test_organization_tablename(self) -> None:
        """Test Organization model has correct table name."""
        assert Organization.__tablename__ == "organizations"


class TestOrganizationCreate:
    """Tests for OrganizationCreate schema."""

    def test_create_with_name(self) -> None:
        """Test OrganizationCreate with valid name."""
        schema = OrganizationCreate(name="Test Clinic")

        assert schema.name == "Test Clinic"

    def test_create_requires_name(self) -> None:
        """Test OrganizationCreate requires name field."""
        with pytest.raises(ValidationError):
            OrganizationCreate()  # type: ignore[call-arg]

    def test_create_name_min_length(self) -> None:
        """Test OrganizationCreate enforces minimum name length."""
        with pytest.raises(ValidationError):
            OrganizationCreate(name="")

    def test_create_name_max_length(self) -> None:
        """Test OrganizationCreate enforces maximum name length."""
        with pytest.raises(ValidationError):
            OrganizationCreate(name="x" * 256)


class TestOrganizationRead:
    """Tests for OrganizationRead schema."""

    def test_read_from_dict(self) -> None:
        """Test OrganizationRead can be created from dict."""
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "name": "Test Clinic",
            "created_at": now,
            "updated_at": now,
        }

        schema = OrganizationRead.model_validate(data)

        assert schema.name == "Test Clinic"
        assert schema.created_at == now

    def test_read_from_orm(self) -> None:
        """Test OrganizationRead can be created from ORM object."""
        # Simulate ORM object with attributes
        class FakeORM:
            id = uuid.uuid4()
            name = "Test Clinic"
            created_at = datetime.now(UTC)
            updated_at = datetime.now(UTC)

        schema = OrganizationRead.model_validate(FakeORM())

        assert schema.name == "Test Clinic"

    def test_read_requires_all_fields(self) -> None:
        """Test OrganizationRead requires all fields."""
        with pytest.raises(ValidationError):
            OrganizationRead(name="Test")  # type: ignore[call-arg]
