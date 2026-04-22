"""Tests for MagicLinkService."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, UnauthorizedError
from src.models.db.magic_link import MagicLink
from src.models.db.user import User, UserRole
from src.services.magic_link_service import MagicLinkService


def _mock_settings() -> MagicMock:
    s = MagicMock()
    s.magic_link_ttl_seconds = 600
    s.jwt_secret = "test-secret"
    s.jwt_algorithm = "HS256"
    return s


def _mock_user(user_id: uuid.UUID, role: UserRole, org_id: uuid.UUID) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.role = role
    u.organization_id = org_id
    u.email = "patient@example.com"
    return u


def _mock_link(
    patient_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
    used_at: datetime | None = None,
) -> MagicMock:
    link = MagicMock(spec=MagicLink)
    link.id = uuid.uuid4()
    link.patient_id = patient_id
    link.token_hash = token_hash
    link.expires_at = expires_at
    link.used_at = used_at
    return link


@pytest.fixture
def service() -> MagicLinkService:
    svc = MagicLinkService(db_session=MagicMock(), settings=_mock_settings())
    svc.repo = MagicMock()
    svc.auth_service = MagicMock()
    return svc


@pytest.mark.asyncio
async def test_issue_link_success(service: MagicLinkService) -> None:
    patient_id = uuid.uuid4()
    therapist_id = uuid.uuid4()
    org_id = uuid.uuid4()

    service.auth_service.get_user_by_id = AsyncMock(
        return_value=_mock_user(patient_id, UserRole.PATIENT, org_id)
    )
    service.repo.create = AsyncMock(
        return_value=_mock_link(patient_id, "hash", datetime.now(UTC))
    )

    token, expires = await service.issue_link(
        patient_id=patient_id,
        created_by_user_id=therapist_id,
        organization_id=org_id,
    )
    assert len(token) > 20
    assert expires > datetime.now(UTC)
    service.repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_issue_link_rejects_non_patient(service: MagicLinkService) -> None:
    patient_id = uuid.uuid4()
    org_id = uuid.uuid4()
    service.auth_service.get_user_by_id = AsyncMock(
        return_value=_mock_user(patient_id, UserRole.THERAPIST, org_id)
    )
    with pytest.raises(UnauthorizedError):
        await service.issue_link(
            patient_id=patient_id,
            created_by_user_id=uuid.uuid4(),
            organization_id=org_id,
        )


@pytest.mark.asyncio
async def test_issue_link_rejects_cross_org(service: MagicLinkService) -> None:
    patient_id = uuid.uuid4()
    service.auth_service.get_user_by_id = AsyncMock(
        return_value=_mock_user(patient_id, UserRole.PATIENT, uuid.uuid4())
    )
    with pytest.raises(NotFoundError):
        await service.issue_link(
            patient_id=patient_id,
            created_by_user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_consume_link_success(service: MagicLinkService) -> None:
    raw_token = "raw-abc-123"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    patient_id = uuid.uuid4()
    org_id = uuid.uuid4()

    service.repo.get_by_token_hash = AsyncMock(
        return_value=_mock_link(
            patient_id,
            token_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    service.repo.mark_used = AsyncMock()
    service.auth_service.get_user_by_id = AsyncMock(
        return_value=_mock_user(patient_id, UserRole.PATIENT, org_id)
    )

    patient, jwt, _ = await service.consume_link(raw_token)
    assert patient.id == patient_id
    assert jwt
    service.repo.mark_used.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_link_rejects_unknown(service: MagicLinkService) -> None:
    service.repo.get_by_token_hash = AsyncMock(return_value=None)
    with pytest.raises(UnauthorizedError):
        await service.consume_link("nope")


@pytest.mark.asyncio
async def test_consume_link_rejects_expired(service: MagicLinkService) -> None:
    raw_token = "expired-token"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    service.repo.get_by_token_hash = AsyncMock(
        return_value=_mock_link(
            uuid.uuid4(),
            token_hash,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    with pytest.raises(UnauthorizedError):
        await service.consume_link(raw_token)


@pytest.mark.asyncio
async def test_consume_link_rejects_already_used(service: MagicLinkService) -> None:
    raw_token = "used-token"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    service.repo.get_by_token_hash = AsyncMock(
        return_value=_mock_link(
            uuid.uuid4(),
            token_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            used_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    with pytest.raises(UnauthorizedError):
        await service.consume_link(raw_token)
