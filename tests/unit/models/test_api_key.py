"""Tests for API Key model and schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.db.api_key import ApiKey
from src.models.domain.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyRead,
)


class TestApiKeyModel:
    """Tests for ApiKey database model."""

    def test_api_key_creation(self) -> None:
        """Test ApiKey model can be instantiated."""
        org_id = uuid.uuid4()
        api_key = ApiKey(
            organization_id=org_id,
            key_hash="hashed_key_value",
            name="Test Key",
            is_active=True,
        )

        assert api_key.organization_id == org_id
        assert api_key.key_hash == "hashed_key_value"
        assert api_key.name == "Test Key"
        assert api_key.is_active is True

    def test_api_key_has_uuid_id(self) -> None:
        """Test ApiKey model has UUID primary key."""
        id_type = ApiKey.__table__.c.id.type
        assert id_type.__class__.__name__ == "UUID"

    def test_api_key_tablename(self) -> None:
        """Test ApiKey model has correct table name."""
        assert ApiKey.__tablename__ == "api_keys"

    def test_api_key_has_organization_fk(self) -> None:
        """Test ApiKey model has foreign key to organization."""
        org_id_col = ApiKey.__table__.c.organization_id
        fk = list(org_id_col.foreign_keys)[0]
        assert fk.column.table.name == "organizations"

    def test_api_key_default_is_active(self) -> None:
        """Test ApiKey column has default=True for is_active."""
        # SQLAlchemy defaults are applied at INSERT time, not Python instantiation
        # So we verify the column default is configured correctly
        is_active_col = ApiKey.__table__.c.is_active
        assert is_active_col.default.arg is True


class TestApiKeyCreate:
    """Tests for ApiKeyCreate schema."""

    def test_create_with_valid_data(self) -> None:
        """Test ApiKeyCreate with valid data."""
        org_id = uuid.uuid4()
        schema = ApiKeyCreate(
            name="Production Key",
            organization_id=org_id,
        )

        assert schema.name == "Production Key"
        assert schema.organization_id == org_id

    def test_create_requires_name(self) -> None:
        """Test ApiKeyCreate requires name field."""
        with pytest.raises(ValidationError):
            ApiKeyCreate(organization_id=uuid.uuid4())  # type: ignore[call-arg]

    def test_create_name_min_length(self) -> None:
        """Test ApiKeyCreate enforces minimum name length."""
        with pytest.raises(ValidationError):
            ApiKeyCreate(name="", organization_id=uuid.uuid4())


class TestApiKeyCreateResponse:
    """Tests for ApiKeyCreateResponse schema."""

    def test_create_response_includes_key(self) -> None:
        """Test ApiKeyCreateResponse includes the plaintext key."""
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "organization_id": uuid.uuid4(),
            "name": "Test Key",
            "key": "trag_abc123",
            "created_at": now,
        }

        schema = ApiKeyCreateResponse.model_validate(data)

        assert schema.key == "trag_abc123"
        assert schema.name == "Test Key"


class TestApiKeyRead:
    """Tests for ApiKeyRead schema."""

    def test_read_does_not_include_key(self) -> None:
        """Test ApiKeyRead does not include the plaintext key."""
        now = datetime.now(UTC)
        data = {
            "id": uuid.uuid4(),
            "organization_id": uuid.uuid4(),
            "name": "Test Key",
            "is_active": True,
            "last_used_at": now,
            "revoked_at": None,
            "created_at": now,
            "updated_at": now,
        }

        schema = ApiKeyRead.model_validate(data)

        assert schema.name == "Test Key"
        assert schema.is_active is True
        # Verify key is not in the model
        assert not hasattr(schema, "key") or getattr(schema, "key", None) is None

    def test_read_from_orm(self) -> None:
        """Test ApiKeyRead can be created from ORM-like object."""

        class FakeORM:
            id = uuid.uuid4()
            organization_id = uuid.uuid4()
            name = "Test Key"
            is_active = True
            last_used_at = datetime.now(UTC)
            revoked_at = None
            created_at = datetime.now(UTC)
            updated_at = datetime.now(UTC)

        schema = ApiKeyRead.model_validate(FakeORM())

        assert schema.name == "Test Key"
        assert schema.is_active is True
