"""Patient-authenticated self-service endpoints.

Distinct from ``/patients`` (therapist-facing clinical views), this
router is mounted at ``/patient`` and resolves the active patient from
the ``therapyrag_patient`` JWT cookie (via ``CurrentPatient``). Every
route is scoped implicitly to the authenticated patient — no path or
query ``patient_id`` is accepted, which makes it impossible for one
patient to enumerate or read another's data.

PHI boundary: patient-facing recap views are returned via
:class:`PatientRecapView`, which is a narrower schema than
:class:`SessionRecapRead`. Therapist notes, risk flags, emotional-tone
interpretation, and the raw transcript are never serialized to patients.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.v1.dependencies import CurrentPatient, Events
from src.core.data_access_audit import log_data_access
from src.core.database import DbSession
from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.domain.auth import CurrentPatient as CurrentPatientSchema
from src.models.domain.session import SessionSummary
from src.models.domain.session_recap import PatientRecapView
from src.services.session_service import SessionService
from src.services.summarization_service import SummarizationService

router = APIRouter()


def get_session_service(session: DbSession) -> SessionService:
    """Get a session service (no tenant context — patient scoping is
    enforced by filtering on the authenticated patient's own id)."""
    return SessionService(session)


def get_summarization_service(session: DbSession) -> SummarizationService:
    return SummarizationService(session)


SessionSvc = Annotated[SessionService, Depends(get_session_service)]
SummarySvc = Annotated[SummarizationService, Depends(get_summarization_service)]


@router.get("/me", response_model=CurrentPatientSchema)
async def get_patient_me(patient: CurrentPatient) -> CurrentPatientSchema:
    """Return the authenticated patient's own identity.

    Mirrors ``GET /auth/patient/me`` but lives under ``/patient`` so the
    web app can fetch self-profile data alongside the rest of the
    patient dashboard without a separate auth call.
    """
    return CurrentPatientSchema.model_validate(patient)


@router.get("/sessions", response_model=list[SessionSummary])
async def list_own_sessions(
    patient: CurrentPatient,
    service: SessionSvc,
    events: Events,
) -> list[SessionSummary]:
    """List the authenticated patient's own therapy sessions.

    Scoped by the patient id derived from the patient session cookie.
    The backend never accepts a caller-supplied patient id on this
    router, which is what makes cross-patient enumeration impossible.
    """
    sessions = await service.get_sessions_for_patient(patient_id=patient.id)

    await log_data_access(
        events,
        actor_id=patient.id,
        organization_id=patient.organization_id,
        subject="patient",
        event_name="patient_portal.sessions_listed",
        properties={"result_count": len(sessions)},
    )

    return sessions


@router.get(
    "/sessions/{session_id}/recap",
    response_model=PatientRecapView,
)
async def get_own_session_recap(
    session_id: uuid.UUID,
    patient: CurrentPatient,
    service: SessionSvc,
    summary_service: SummarySvc,
    events: Events,
) -> PatientRecapView:
    """Get the patient-safe recap for one of the patient's own sessions.

    Returns a narrower view than the therapist recap endpoint:
    therapist_notes, risk_flags, emotional_tone, and the raw transcript
    are never included.

    Raises 404 if the session or its recap doesn't exist, and 403 if the
    session belongs to a different patient (even inside the same
    organization). Both checks matter: 404 alone would leak existence of
    other patients' sessions via a timing/404 oracle.
    """
    session = await service.session_repo.get_by_id(session_id)
    if session is None:
        raise NotFoundError(resource="Session", resource_id=str(session_id))
    if session.patient_id != patient.id:
        raise ForbiddenError(
            detail="Session does not belong to the authenticated patient."
        )

    recap = await summary_service.get_recap(session_id)

    view = PatientRecapView(
        session_id=recap.session_id,
        session_date=session.session_date,
        brief=recap.brief,
        key_topics=list(recap.key_topics),
        homework_assigned=list(recap.homework_assigned),
        follow_ups=list(recap.follow_ups),
        generated_at=recap.generated_at,
    )

    await log_data_access(
        events,
        actor_id=patient.id,
        organization_id=patient.organization_id,
        subject="patient",
        event_name="patient_portal.recap_viewed",
        properties={"session_id": str(session_id)},
    )

    return view
