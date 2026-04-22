"""Therapist-facing patient endpoints.

Patient themes and chatbot conversation review, plus HIPAA data-rights
endpoints (export and hard delete). These are distinct from /users/
which handles user CRUD; this router exposes clinical views that are
only meaningful in the context of an authenticated therapist reviewing
their patient.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.v1.dependencies import Auth, Events
from src.core.database import DbSession
from src.core.exceptions import ValidationError
from src.models.db.event import EventCategory
from src.models.domain.assessment import (
    AssessmentCreate,
    AssessmentInstrument,
    AssessmentRead,
)
from src.models.domain.chat import ConversationRead, ConversationSummary
from src.models.domain.patient_themes import PatientThemesRead
from src.services.assessment_service import AssessmentService
from src.services.auth_service import AuthService
from src.services.conversation_service import ConversationService
from src.services.data_export_service import DataExportService
from src.services.themes_service import ThemesService

router = APIRouter()


def get_themes_service(session: DbSession) -> ThemesService:
    return ThemesService(session)


def get_conversation_service(session: DbSession) -> ConversationService:
    return ConversationService(session)


def get_assessment_service(session: DbSession) -> AssessmentService:
    return AssessmentService(session)


def get_data_export_service(session: DbSession) -> DataExportService:
    return DataExportService(session)


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(session)


ThemesSvc = Annotated[ThemesService, Depends(get_themes_service)]
ConversationSvc = Annotated[ConversationService, Depends(get_conversation_service)]
AssessmentSvc = Annotated[AssessmentService, Depends(get_assessment_service)]
DataExportSvc = Annotated[DataExportService, Depends(get_data_export_service)]
AuthSvc = Annotated[AuthService, Depends(get_auth_service)]


class PatientDeleteConfirm(BaseModel):
    """Body for DELETE /patients/{id} — confirms the patient's email to
    guard against fat-fingering the wrong patient id."""

    confirm_email: str = Field(..., min_length=3, max_length=255)


class PatientDeleteResponse(BaseModel):
    patient_id: str
    session_count_deleted: int
    transcript_count_deleted: int
    conversation_count_deleted: int
    deleted_at: str


@router.get(
    "/{patient_id}/themes",
    response_model=PatientThemesRead,
)
async def get_patient_themes(
    patient_id: uuid.UUID,
    service: ThemesSvc,
) -> PatientThemesRead:
    """Get the most recent synthesized theme document for a patient.

    Returns 404 if themes haven't been generated yet. Use POST to
    generate or refresh.
    """
    return await service.get_themes(patient_id)


@router.post(
    "/{patient_id}/themes",
    response_model=PatientThemesRead,
    status_code=201,
)
async def generate_patient_themes(
    patient_id: uuid.UUID,
    service: ThemesSvc,
    auth: Auth,
    events: Events,
) -> PatientThemesRead:
    """Synthesize themes across a patient's session recaps.

    Requires at least 2 ready session recaps. Runs synchronously. The
    resulting document overwrites any prior themes for this patient.
    """
    themes = await service.generate_themes(patient_id)
    await events.publish(
        event_name="patient.themes_generated",
        category=EventCategory.SYSTEM,
        organization_id=auth.organization_id,
        properties={
            "patient_id": str(patient_id),
            "source_session_count": themes.source_session_count,
            "model": themes.model_name,
        },
    )
    return themes


@router.get(
    "/{patient_id}/conversations",
    response_model=list[ConversationSummary],
)
async def list_patient_conversations(
    patient_id: uuid.UUID,
    service: ConversationSvc,
    auth: Auth,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationSummary]:
    """List the patient's chatbot conversations for therapist review.

    Returns conversation summaries (no message bodies) sorted by most
    recently updated. Scoped to the authenticated therapist's org.
    """
    return await service.list_for_therapist(
        patient_id=patient_id,
        organization_id=auth.organization_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{patient_id}/conversations/{conversation_id}",
    response_model=ConversationRead,
)
async def get_patient_conversation(
    patient_id: uuid.UUID,  # noqa: ARG001  # path param; access control via org_id
    conversation_id: uuid.UUID,
    service: ConversationSvc,
    auth: Auth,
) -> ConversationRead:
    """Get a single conversation with all messages, for therapist review.

    Returns 404 if the conversation doesn't exist or doesn't belong to
    the authenticated therapist's org. The patient_id in the path is
    informational only — access control is via organization_id.
    """
    return await service.get_for_therapist(
        conversation_id=conversation_id,
        organization_id=auth.organization_id,
    )


@router.post(
    "/{patient_id}/assessments",
    response_model=AssessmentRead,
    status_code=201,
)
async def record_patient_assessment(
    patient_id: uuid.UUID,
    payload: AssessmentCreate,
    service: AssessmentSvc,
    auth: Auth,
    events: Events,
) -> AssessmentRead:
    """Record a PHQ-9 or GAD-7 assessment for a patient.

    Score and severity are computed server-side from the responses.
    Severity bands follow the standard clinical cutpoints (minimal,
    mild, moderate, moderately severe, severe).
    """
    result = await service.record(
        patient_id=patient_id,
        administered_by_user_id=auth.api_key_id,
        payload=payload,
    )
    await events.publish(
        event_name="assessment.recorded",
        category=EventCategory.USER_ACTION,
        organization_id=auth.organization_id,
        actor_id=auth.api_key_id,
        properties={
            "patient_id": str(patient_id),
            "instrument": payload.instrument.value,
            "total_score": result.total_score,
            "severity": result.severity,
        },
    )
    return result


@router.get(
    "/{patient_id}/assessments",
    response_model=list[AssessmentRead],
)
async def list_patient_assessments(
    patient_id: uuid.UUID,
    service: AssessmentSvc,
    instrument: Annotated[
        AssessmentInstrument | None,
        Query(description="Filter by instrument"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AssessmentRead]:
    """List a patient's assessments, newest first."""
    return await service.list_for_patient(
        patient_id=patient_id,
        instrument=instrument,
        limit=limit,
    )


@router.get("/{patient_id}/export")
async def export_patient_data(
    patient_id: uuid.UUID,
    service: DataExportSvc,
    auth: Auth,
    events: Events,
) -> dict[str, Any]:
    """HIPAA right-to-access: return every piece of patient data as JSON.

    Scoped to the authenticated therapist's organization. Publishes a
    ``patient.data_exported`` event so the export is discoverable in the
    audit log.
    """
    bundle = await service.export_patient(
        patient_id=patient_id,
        org_id=auth.organization_id,
    )
    await events.publish(
        event_name="patient.data_exported",
        category=EventCategory.SYSTEM,
        organization_id=auth.organization_id,
        actor_id=auth.api_key_id,
        properties={
            "patient_id": str(patient_id),
            "session_count": len(bundle.get("sessions", [])),
            "conversation_count": len(bundle.get("conversations", [])),
        },
    )
    return bundle


@router.delete("/{patient_id}", response_model=PatientDeleteResponse)
async def delete_patient_data(
    patient_id: uuid.UUID,
    payload: PatientDeleteConfirm,
    service: DataExportSvc,
    auth_service: AuthSvc,
    auth: Auth,
) -> PatientDeleteResponse:
    """HIPAA right-to-deletion: hard-delete a patient and cascade data.

    Requires a confirmation body echoing the patient's email so the
    therapist can't fat-finger the wrong id. The service writes a
    tombstone analytics event before cascading the delete.
    """
    patient = await auth_service.get_user_by_id(patient_id)
    if patient.email.strip().lower() != payload.confirm_email.strip().lower():
        raise ValidationError(
            detail="confirm_email does not match the patient's email address",
        )

    summary = await service.delete_patient(
        patient_id=patient_id,
        org_id=auth.organization_id,
        therapist_id=auth.api_key_id,
    )
    return PatientDeleteResponse(**summary)
