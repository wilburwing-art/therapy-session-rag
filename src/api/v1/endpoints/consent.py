"""Consent API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from src.api.v1.dependencies import Auth, Events
from src.core.database import DbSession
from src.models.db.event import EventCategory
from src.models.domain.consent import (
    ConsentAuditEntry,
    ConsentCheck,
    ConsentGrant,
    ConsentRead,
    ConsentRevoke,
)
from src.models.domain.consent import ConsentType as DomainConsentType
from src.services.consent_service import ConsentService

router = APIRouter()


def get_consent_service(session: DbSession) -> ConsentService:
    """Get consent service instance."""
    return ConsentService(session)


ConsentSvc = Annotated[ConsentService, Depends(get_consent_service)]


def get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extract IP address and user agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


@router.post("", response_model=ConsentRead, status_code=201)
async def grant_consent(
    grant: ConsentGrant,
    request: Request,
    auth: Auth,
    service: ConsentSvc,
    events: Events,
) -> ConsentRead:
    """Grant consent for a patient.

    Creates a new consent record with status='granted'.
    Returns 409 Conflict if active consent already exists for this type.
    """
    ip_address, user_agent = get_client_info(request)
    result = await service.grant_consent(
        grant=grant,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await events.publish(
        event_name="consent.granted",
        category=EventCategory.USER_ACTION,
        organization_id=auth.organization_id,
        actor_id=grant.patient_id,
        properties={
            "consent_type": grant.consent_type.value,
            "therapist_id": str(grant.therapist_id),
        },
    )

    return result


@router.delete("", response_model=ConsentRead)
async def revoke_consent(
    revoke: ConsentRevoke,
    request: Request,
    auth: Auth,
    service: ConsentSvc,
    events: Events,
) -> ConsentRead:
    """Revoke consent for a patient.

    Creates a new revocation record (immutable pattern).
    Returns 404 if no active consent exists to revoke.
    """
    ip_address, user_agent = get_client_info(request)
    result = await service.revoke_consent(
        revoke=revoke,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    await events.publish(
        event_name="consent.revoked",
        category=EventCategory.USER_ACTION,
        organization_id=auth.organization_id,
        actor_id=revoke.patient_id,
        properties={
            "consent_type": revoke.consent_type.value,
            "therapist_id": str(revoke.therapist_id),
        },
    )

    return result


@router.get("/{patient_id}/check", response_model=ConsentCheck)
async def check_consent(
    patient_id: uuid.UUID,
    therapist_id: Annotated[uuid.UUID, Query(description="Therapist ID")],
    consent_type: Annotated[DomainConsentType, Query(description="Type of consent")],
    auth: Auth,  # noqa: ARG001
    service: ConsentSvc,
) -> ConsentCheck:
    """Check if consent is currently active for a patient.

    Returns has_consent=True if an active consent exists for the
    patient/therapist/type combination.
    """
    return await service.check_consent(
        patient_id=patient_id,
        therapist_id=therapist_id,
        consent_type=consent_type,
    )


@router.get("/{patient_id}/active", response_model=list[ConsentRead])
async def get_active_consents(
    patient_id: uuid.UUID,
    therapist_id: Annotated[uuid.UUID, Query(description="Therapist ID")],
    auth: Auth,  # noqa: ARG001
    service: ConsentSvc,
) -> list[ConsentRead]:
    """Get all active consents for a patient/therapist combination.

    Returns a list of all consent types that are currently active.
    """
    return await service.get_all_active(
        patient_id=patient_id,
        therapist_id=therapist_id,
    )


@router.get("/{patient_id}/audit", response_model=list[ConsentAuditEntry])
async def get_consent_audit_log(
    patient_id: uuid.UUID,
    therapist_id: Annotated[uuid.UUID, Query(description="Therapist ID")],
    auth: Auth,  # noqa: ARG001
    service: ConsentSvc,
    consent_type: Annotated[
        DomainConsentType | None, Query(description="Optional filter by consent type")
    ] = None,
) -> list[ConsentAuditEntry]:
    """Get the complete consent history for a patient.

    Returns all consent records (grants and revocations) ordered by
    granted_at descending. Optionally filter by consent_type.
    """
    return await service.get_audit_log(
        patient_id=patient_id,
        therapist_id=therapist_id,
        consent_type=consent_type,
    )
