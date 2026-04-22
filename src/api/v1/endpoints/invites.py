"""Therapist invite endpoints.

An authenticated therapist can issue, list, and revoke invites for new
teammates joining the practice. The invite recipient redeems the token
from the emailed link (or a copy-pasted URL) and sets a password; the
accept endpoint logs them in by setting the therapist session cookie.
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from src.api.v1.dependencies import CurrentTherapist, Events
from src.core.config import Settings, get_settings
from src.core.csrf import new_csrf_token, set_csrf_cookie
from src.core.database import DbSession
from src.models.db.event import EventCategory
from src.models.db.therapist_invite import TherapistInviteRole
from src.models.domain.auth import LoginResponse
from src.models.domain.invite import (
    InviteAcceptRequest,
    InviteCreate,
    InviteCreateResponse,
    InviteRead,
    InviteRole,
)
from src.services.email_service import EmailService, EmailServiceError
from src.services.invite_service import InviteService

router = APIRouter()
logger = logging.getLogger(__name__)


def get_invite_service(session: DbSession) -> InviteService:
    return InviteService(session)


def get_email_service() -> EmailService:
    return EmailService()


InviteSvc = Annotated[InviteService, Depends(get_invite_service)]
EmailSvc = Annotated[EmailService, Depends(get_email_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _set_session_cookie(
    response: Response,
    token: str,
    settings: Settings,
) -> None:
    """Set the therapist session + CSRF cookies.

    Duplicated from auth.py on purpose: a 6-line helper is cheaper to
    inline than to import from another endpoint module.
    """
    response.set_cookie(
        key=settings.jwt_cookie_name,
        value=token,
        max_age=settings.jwt_access_token_ttl_seconds,
        httponly=True,
        secure=settings.jwt_cookie_secure,
        samesite="lax",
        path="/",
    )
    set_csrf_cookie(response, new_csrf_token(), settings)


@router.post(
    "",
    response_model=InviteCreateResponse,
    status_code=201,
)
async def create_invite(
    payload: InviteCreate,
    invite_service: InviteSvc,
    email_service: EmailSvc,
    events: Events,
    settings: SettingsDep,
    therapist: CurrentTherapist,
) -> InviteCreateResponse:
    """Issue an invite for a new therapist to join the practice.

    Sends an invite email (best-effort) and returns the raw token so
    the inviter can copy the accept URL if email delivery failed.
    """
    invite, raw_token, expires_at = await invite_service.issue_invite(
        organization_id=therapist.organization_id,
        inviter_id=therapist.id,
        email=payload.email,
        role=TherapistInviteRole(payload.role.value),
    )

    invite_url = f"{settings.web_app_url}/accept-invite?t={raw_token}"
    practice_name = (
        therapist.organization.name
        if therapist.organization is not None
        else "your practice"
    )
    inviter_name = therapist.full_name or therapist.email
    try:
        email_service.send_therapist_invite(
            to_email=invite.email,
            practice_name=practice_name,
            inviter_name=inviter_name,
            invite_url=invite_url,
            role=invite.role.value,
        )
    except EmailServiceError as exc:
        logger.warning(
            "Failed to email invite to %s: %s", invite.email, exc
        )

    await events.publish(
        event_name="invite.sent",
        category=EventCategory.USER_ACTION,
        organization_id=therapist.organization_id,
        actor_id=therapist.id,
        properties={
            "invite_id": str(invite.id),
            "invitee_email": invite.email,
            "role": invite.role.value,
        },
    )

    return InviteCreateResponse(
        id=invite.id,
        email=invite.email,
        role=InviteRole(invite.role.value),
        token=raw_token,
        expires_at=expires_at,
    )


@router.get("", response_model=list[InviteRead])
async def list_invites(
    invite_service: InviteSvc,
    therapist: CurrentTherapist,
) -> list[InviteRead]:
    """List pending and accepted invites for the caller's organization."""
    invites = await invite_service.list_invites(therapist.organization_id)
    return [InviteRead.model_validate(inv) for inv in invites]


@router.delete("/{invite_id}", status_code=204)
async def delete_invite(
    invite_id: uuid.UUID,
    invite_service: InviteSvc,
    events: Events,
    therapist: CurrentTherapist,
) -> Response:
    """Revoke a pending invite. Accepted invites cannot be revoked."""
    await invite_service.revoke_invite(
        organization_id=therapist.organization_id,
        invite_id=invite_id,
    )
    await events.publish(
        event_name="invite.revoked",
        category=EventCategory.USER_ACTION,
        organization_id=therapist.organization_id,
        actor_id=therapist.id,
        properties={"invite_id": str(invite_id)},
    )
    return Response(status_code=204)


@router.post("/accept", response_model=LoginResponse)
async def accept_invite(
    payload: InviteAcceptRequest,
    response: Response,
    invite_service: InviteSvc,
    events: Events,
    settings: SettingsDep,
) -> LoginResponse:
    """Redeem an invite token, create the therapist user, and log them in.

    Public endpoint: the user isn't authenticated yet. CSRF-exempt (see
    `src/core/csrf.py`). Returns a `LoginResponse`-shaped body so the
    frontend can reuse the same redirect logic as `/auth/login`.
    """
    user, token, expires_at = await invite_service.accept_invite(
        raw_token=payload.token,
        password=payload.password,
        full_name=payload.full_name,
    )
    _set_session_cookie(response, token, settings)

    await events.publish(
        event_name="invite.accepted",
        category=EventCategory.USER_ACTION,
        organization_id=user.organization_id,
        actor_id=user.id,
        properties={"email": user.email},
    )

    return LoginResponse(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        expires_at=expires_at,
    )
