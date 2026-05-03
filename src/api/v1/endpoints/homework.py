"""Homework API endpoints for the authenticated patient.

The patient web app uses these to list between-session tasks and mark
them complete. Access is scoped to the patient JWT — a patient can
only ever see and mutate their own homework. Therapist-side read is
exposed separately from /patients/{id}/homework.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.v1.dependencies import CurrentPatient, Events
from src.core.data_access_audit import log_data_access
from src.core.database import DbSession
from src.models.domain.homework import HomeworkItemRead, HomeworkItemToggle
from src.services.homework_service import HomeworkService

router = APIRouter()


def get_homework_service(session: DbSession) -> HomeworkService:
    return HomeworkService(session)


HomeworkSvc = Annotated[HomeworkService, Depends(get_homework_service)]


@router.get("/me", response_model=list[HomeworkItemRead])
async def list_my_homework(
    patient: CurrentPatient,
    service: HomeworkSvc,
    completed: Annotated[
        bool | None,
        Query(description="Filter by completion state. Omit for all."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[HomeworkItemRead]:
    """List the authenticated patient's homework, newest session first."""
    return await service.list_for_patient(
        patient_id=patient.id,
        organization_id=patient.organization_id,
        completed=completed,
        limit=limit,
    )


@router.patch("/{homework_id}", response_model=HomeworkItemRead)
async def toggle_my_homework(
    homework_id: uuid.UUID,
    payload: HomeworkItemToggle,
    patient: CurrentPatient,
    service: HomeworkSvc,
    events: Events,
) -> HomeworkItemRead:
    """Mark a homework item complete or incomplete.

    404 if the item doesn't belong to the authenticated patient.
    """
    result = await service.toggle_completion(
        homework_id=homework_id,
        patient_id=patient.id,
        completed=payload.completed,
    )
    await log_data_access(
        events,
        actor_id=patient.id,
        organization_id=patient.organization_id,
        subject="patient",
        event_name="patient.homework_updated",
        properties={
            "homework_id": str(homework_id),
            "completed": payload.completed,
        },
    )
    return result
