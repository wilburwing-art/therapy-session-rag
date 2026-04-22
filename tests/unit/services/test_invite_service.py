"""Tests for InviteService."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.models.db.therapist_invite import TherapistInvite, TherapistInviteRole
from src.models.db.user import User, UserRole
from src.services.invite_service import InviteService


def _mock_settings() -> MagicMock:
    s = MagicMock()
    s.magic_link_ttl_seconds = 600
    s.jwt_access_token_ttl_seconds = 3600
    s.jwt_secret = "test-secret"
    s.jwt_algorithm = "HS256"
    return s


def _mock_invite(
    organization_id: uuid.UUID,
    email: str,
    token_hash: str,
    expires_at: datetime,
    accepted_at: datetime | None = None,
    role: TherapistInviteRole = TherapistInviteRole.THERAPIST,
) -> MagicMock:
    inv = MagicMock(spec=TherapistInvite)
    inv.id = uuid.uuid4()
    inv.organization_id = organization_id
    inv.email = email
    inv.role = role
    inv.token_hash = token_hash
    inv.expires_at = expires_at
    inv.accepted_at = accepted_at
    inv.invited_by_user_id = uuid.uuid4()
    return inv


def _mock_user(user_id: uuid.UUID, role: UserRole, org_id: uuid.UUID) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = user_id
    u.role = role
    u.organization_id = org_id
    u.email = "user@example.com"
    u.full_name = "Jane Therapist"
    return u


@pytest.fixture
def service() -> InviteService:
    svc = InviteService(db_session=MagicMock(), settings=_mock_settings())
    svc.db_session = MagicMock()
    svc.db_session.add = MagicMock()
    svc.db_session.flush = AsyncMock()
    svc.db_session.refresh = AsyncMock()
    svc.repo = MagicMock()
    svc.auth_service = MagicMock()
    return svc


@pytest.mark.asyncio
async def test_issue_invite_success(service: InviteService) -> None:
    org_id = uuid.uuid4()
    inviter_id = uuid.uuid4()

    service.auth_service.get_user_by_email = AsyncMock(return_value=None)
    service.repo.get_pending_for_org_and_email = AsyncMock(return_value=None)
    service.repo.create = AsyncMock(
        return_value=_mock_invite(
            org_id,
            "new@example.com",
            "hash",
            datetime.now(UTC) + timedelta(days=7),
        )
    )

    invite, raw_token, expires_at = await service.issue_invite(
        organization_id=org_id,
        inviter_id=inviter_id,
        email="New@Example.com",
        role=TherapistInviteRole.THERAPIST,
    )

    assert len(raw_token) > 20
    assert expires_at > datetime.now(UTC)
    service.repo.create.assert_awaited_once()
    # Email should be lowercased when passed to the repo
    call_kwargs = service.repo.create.await_args.kwargs
    assert call_kwargs["email"] == "new@example.com"
    assert invite.email == "new@example.com"


@pytest.mark.asyncio
async def test_issue_invite_rejects_duplicate_email(service: InviteService) -> None:
    org_id = uuid.uuid4()
    existing_user = _mock_user(uuid.uuid4(), UserRole.THERAPIST, uuid.uuid4())
    service.auth_service.get_user_by_email = AsyncMock(return_value=existing_user)

    with pytest.raises(ConflictError):
        await service.issue_invite(
            organization_id=org_id,
            inviter_id=uuid.uuid4(),
            email="taken@example.com",
        )


@pytest.mark.asyncio
async def test_issue_invite_rejects_pending_invite(service: InviteService) -> None:
    org_id = uuid.uuid4()
    service.auth_service.get_user_by_email = AsyncMock(return_value=None)
    service.repo.get_pending_for_org_and_email = AsyncMock(
        return_value=_mock_invite(
            org_id,
            "pending@example.com",
            "hash",
            datetime.now(UTC) + timedelta(days=7),
        )
    )

    with pytest.raises(ConflictError):
        await service.issue_invite(
            organization_id=org_id,
            inviter_id=uuid.uuid4(),
            email="pending@example.com",
        )


@pytest.mark.asyncio
async def test_accept_invite_success_creates_user_and_returns_jwt(
    service: InviteService,
) -> None:
    raw_token = "raw-invite-token-xyz"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    org_id = uuid.uuid4()

    invite = _mock_invite(
        org_id,
        "invitee@example.com",
        token_hash,
        datetime.now(UTC) + timedelta(days=7),
    )
    service.repo.get_by_token_hash = AsyncMock(return_value=invite)
    service.repo.mark_accepted = AsyncMock()
    service.auth_service.get_user_by_email = AsyncMock(return_value=None)

    user, jwt_token, expires_at = await service.accept_invite(
        raw_token=raw_token,
        password="secret-password",
        full_name="Newly Joined Therapist",
    )

    assert jwt_token
    assert expires_at > datetime.now(UTC)
    assert user.email == "invitee@example.com"
    assert user.organization_id == org_id
    assert user.role == UserRole.THERAPIST
    assert user.full_name == "Newly Joined Therapist"
    assert user.password_hash is not None
    service.repo.mark_accepted.assert_awaited_once_with(invite.id)
    service.db_session.add.assert_called_once()


@pytest.mark.asyncio
async def test_accept_invite_rejects_unknown_token(service: InviteService) -> None:
    service.repo.get_by_token_hash = AsyncMock(return_value=None)
    with pytest.raises(UnauthorizedError):
        await service.accept_invite(
            raw_token="nope",
            password="password123",
            full_name="x",
        )


@pytest.mark.asyncio
async def test_accept_invite_rejects_expired(service: InviteService) -> None:
    raw_token = "expired"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    service.repo.get_by_token_hash = AsyncMock(
        return_value=_mock_invite(
            uuid.uuid4(),
            "expired@example.com",
            token_hash,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    with pytest.raises(UnauthorizedError):
        await service.accept_invite(
            raw_token=raw_token,
            password="password123",
            full_name="x",
        )


@pytest.mark.asyncio
async def test_accept_invite_rejects_already_accepted(service: InviteService) -> None:
    raw_token = "already-accepted"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    service.repo.get_by_token_hash = AsyncMock(
        return_value=_mock_invite(
            uuid.uuid4(),
            "done@example.com",
            token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            accepted_at=datetime.now(UTC) - timedelta(minutes=5),
        )
    )
    with pytest.raises(UnauthorizedError):
        await service.accept_invite(
            raw_token=raw_token,
            password="password123",
            full_name="x",
        )


@pytest.mark.asyncio
async def test_revoke_rejects_accepted_invite(service: InviteService) -> None:
    org_id = uuid.uuid4()
    invite_id = uuid.uuid4()
    accepted = _mock_invite(
        org_id,
        "already@example.com",
        "hash",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        accepted_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    accepted.id = invite_id
    service.repo.get_by_id_for_org = AsyncMock(return_value=accepted)
    service.repo.revoke = AsyncMock()

    with pytest.raises(ConflictError):
        await service.revoke_invite(organization_id=org_id, invite_id=invite_id)
    service.repo.revoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_pending_invite_succeeds(service: InviteService) -> None:
    org_id = uuid.uuid4()
    invite_id = uuid.uuid4()
    pending = _mock_invite(
        org_id,
        "pending@example.com",
        "hash",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    pending.id = invite_id
    service.repo.get_by_id_for_org = AsyncMock(return_value=pending)
    service.repo.revoke = AsyncMock()

    await service.revoke_invite(organization_id=org_id, invite_id=invite_id)
    service.repo.revoke.assert_awaited_once_with(invite_id)


@pytest.mark.asyncio
async def test_revoke_unknown_invite_raises_not_found(service: InviteService) -> None:
    service.repo.get_by_id_for_org = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.revoke_invite(
            organization_id=uuid.uuid4(),
            invite_id=uuid.uuid4(),
        )
