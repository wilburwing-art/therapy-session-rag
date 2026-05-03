"""Intake endpoints.

Two surfaces:

- Authenticated therapist endpoints for managing forms and invitations.
- Public (CSRF-exempt) endpoints for a prospective patient to load the
  invitation and submit their answers.
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from src.api.v1.dependencies import CurrentTherapist, Events
from src.core.config import Settings, get_settings
from src.core.database import DbSession
from src.models.db.event import EventCategory
from src.models.db.intake_form import IntakeFormStatus
from src.models.domain.intake import (
    IntakeFormCreate,
    IntakeFormRead,
    IntakeFormUpdate,
    IntakeInvitationCreate,
    IntakeInvitationCreateResponse,
    IntakeInvitationPublic,
    IntakeInvitationRead,
    IntakeInvitationStatusOut,
    IntakeQuestion,
    IntakeResponseRead,
    IntakeSubmission,
)
from src.services.email_service import EmailService, EmailServiceError
from src.services.intake_service import IntakeService

router = APIRouter()
logger = logging.getLogger(__name__)


def get_intake_service(session: DbSession) -> IntakeService:
    return IntakeService(session)


def get_email_service() -> EmailService:
    return EmailService()


IntakeSvc = Annotated[IntakeService, Depends(get_intake_service)]
EmailSvc = Annotated[EmailService, Depends(get_email_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post(
    "/forms",
    response_model=IntakeFormRead,
    status_code=201,
)
async def create_form(
    payload: IntakeFormCreate,
    intake_service: IntakeSvc,
    therapist: CurrentTherapist,
) -> IntakeFormRead:
    """Create a new intake form for the practice."""
    form = await intake_service.create_form(
        organization_id=therapist.organization_id,
        created_by_user_id=therapist.id,
        name=payload.name,
        description=payload.description,
        questions=[q.model_dump() for q in payload.questions],
    )
    return IntakeFormRead.model_validate(form)


@router.get("/forms", response_model=list[IntakeFormRead])
async def list_forms(
    intake_service: IntakeSvc,
    therapist: CurrentTherapist,
) -> list[IntakeFormRead]:
    """List all intake forms for the caller's organization."""
    forms = await intake_service.list_forms(therapist.organization_id)
    return [IntakeFormRead.model_validate(f) for f in forms]


@router.get("/forms/{form_id}", response_model=IntakeFormRead)
async def get_form(
    form_id: uuid.UUID,
    intake_service: IntakeSvc,
    therapist: CurrentTherapist,
) -> IntakeFormRead:
    form = await intake_service.get_form(
        organization_id=therapist.organization_id,
        form_id=form_id,
    )
    return IntakeFormRead.model_validate(form)


@router.patch("/forms/{form_id}", response_model=IntakeFormRead)
async def update_form(
    form_id: uuid.UUID,
    payload: IntakeFormUpdate,
    intake_service: IntakeSvc,
    therapist: CurrentTherapist,
) -> IntakeFormRead:
    status_value: IntakeFormStatus | None = (
        IntakeFormStatus(payload.status.value) if payload.status else None
    )
    questions: list[dict[str, Any]] | None = (
        [q.model_dump() for q in payload.questions] if payload.questions is not None else None
    )
    form = await intake_service.update_form(
        organization_id=therapist.organization_id,
        form_id=form_id,
        name=payload.name,
        description=payload.description,
        status=status_value,
        questions=questions,
    )
    return IntakeFormRead.model_validate(form)


@router.post(
    "/invitations",
    response_model=IntakeInvitationCreateResponse,
    status_code=201,
)
async def create_invitation(
    payload: IntakeInvitationCreate,
    intake_service: IntakeSvc,
    email_service: EmailSvc,
    events: Events,
    settings: SettingsDep,
    therapist: CurrentTherapist,
) -> IntakeInvitationCreateResponse:
    """Issue an intake invitation for a prospective patient.

    Sends an email (best-effort) and returns the raw token so the
    therapist can copy the intake URL if email delivery failed.
    """
    invitation, raw_token, expires_at = await intake_service.issue_invitation(
        organization_id=therapist.organization_id,
        invited_by_user_id=therapist.id,
        form_id=payload.form_id,
        patient_email=payload.patient_email,
        patient_name=payload.patient_name,
    )

    intake_url = f"{settings.web_app_url}/intake?t={raw_token}"
    practice_name = (
        therapist.organization.name if therapist.organization is not None else "your practice"
    )
    therapist_name = therapist.full_name or therapist.email
    try:
        email_service.send_intake_invitation(
            to_email=invitation.patient_email,
            practice_name=practice_name,
            therapist_name=therapist_name,
            intake_url=intake_url,
            patient_name=invitation.patient_name,
        )
    except EmailServiceError as exc:
        logger.warning(
            "Failed to email intake invitation to %s: %s",
            invitation.patient_email,
            exc,
        )

    await events.publish(
        event_name="intake.invitation.sent",
        category=EventCategory.USER_ACTION,
        organization_id=therapist.organization_id,
        actor_id=therapist.id,
        properties={
            "invitation_id": str(invitation.id),
            "form_id": str(invitation.form_id),
            "patient_email": invitation.patient_email,
        },
    )

    return IntakeInvitationCreateResponse(
        id=invitation.id,
        form_id=invitation.form_id,
        patient_email=invitation.patient_email,
        patient_name=invitation.patient_name,
        token=raw_token,
        expires_at=expires_at,
        status=IntakeInvitationStatusOut(invitation.status.value),
    )


@router.get("/invitations", response_model=list[IntakeInvitationRead])
async def list_invitations(
    intake_service: IntakeSvc,
    therapist: CurrentTherapist,
    patient_email: str | None = None,
) -> list[IntakeInvitationRead]:
    """List intake invitations for the caller's org, optionally filtered by email."""
    if patient_email:
        invitations = await intake_service.list_invitations_for_email(
            organization_id=therapist.organization_id,
            patient_email=patient_email,
        )
    else:
        invitations = await intake_service.list_invitations(therapist.organization_id)
    return [IntakeInvitationRead.model_validate(inv) for inv in invitations]


@router.delete("/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    intake_service: IntakeSvc,
    events: Events,
    therapist: CurrentTherapist,
) -> Response:
    """Revoke a pending intake invitation. Submitted invitations cannot be revoked."""
    await intake_service.revoke_invitation(
        organization_id=therapist.organization_id,
        invitation_id=invitation_id,
    )
    await events.publish(
        event_name="intake.invitation.revoked",
        category=EventCategory.USER_ACTION,
        organization_id=therapist.organization_id,
        actor_id=therapist.id,
        properties={"invitation_id": str(invitation_id)},
    )
    return Response(status_code=204)


@router.get(
    "/invitations/lookup",
    response_model=IntakeInvitationPublic,
)
async def lookup_invitation(
    t: str,
    intake_service: IntakeSvc,
) -> IntakeInvitationPublic:
    """Resolve a raw token to the form the patient needs to fill out.

    Public endpoint: used by the intake page before the patient has
    submitted anything.
    """
    invitation, form = await intake_service.load_public_invitation(t)
    practice_name = form.organization.name if form.organization is not None else "Your therapist"
    return IntakeInvitationPublic(
        form_id=form.id,
        practice_name=practice_name,
        patient_name=invitation.patient_name,
        questions=[IntakeQuestion.model_validate(q) for q in form.questions],
        expires_at=invitation.expires_at,
    )


@router.post(
    "/invitations/submit",
    response_model=IntakeResponseRead,
    status_code=201,
)
async def submit_invitation(
    payload: IntakeSubmission,
    request: Request,
    intake_service: IntakeSvc,
) -> IntakeResponseRead:
    """Public endpoint for the patient to submit their intake answers."""
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    response = await intake_service.submit_response(
        raw_token=payload.token,
        answers=payload.answers,
        submitted_ip=client_ip,
        submitted_user_agent=user_agent,
    )
    return IntakeResponseRead.model_validate(response)
