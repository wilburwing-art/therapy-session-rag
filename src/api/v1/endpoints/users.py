"""Users API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.api.v1.dependencies import Auth
from src.core.database import DbSession
from src.core.exceptions import ConflictError, NotFoundError
from src.models.db.user import User
from src.models.db.user import UserRole as DbUserRole
from src.models.domain.user import PatientCreate, UserRead, UserRole

router = APIRouter()


@router.get("", response_model=list[UserRead])
async def list_users(
    auth: Auth,
    session: DbSession,
    role: Annotated[UserRole | None, Query(description="Filter by user role")] = None,
) -> list[UserRead]:
    """List users in the authenticated organization.

    Optionally filter by role (therapist, patient, admin).
    Only returns users from the same organization as the API key.
    """
    query = select(User).where(User.organization_id == auth.organization_id)

    if role is not None:
        query = query.where(User.role == role)

    query = query.order_by(User.email)

    result = await session.execute(query)
    users = result.scalars().all()

    return [UserRead.model_validate(user) for user in users]


@router.post("/patients", response_model=UserRead, status_code=201)
async def create_patient(
    payload: PatientCreate,
    auth: Auth,
    session: DbSession,
) -> UserRead:
    """Create a patient user in the authenticated therapist's org.

    The patient gets no password (they only ever use magic links).
    Returns 409 if the email already exists anywhere in the system.
    """
    normalized_email = payload.email.lower()
    existing = await session.execute(
        select(User).where(User.email == normalized_email)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(detail="A user with this email already exists")

    patient = User(
        organization_id=auth.organization_id,
        email=normalized_email,
        role=DbUserRole.PATIENT,
        full_name=payload.full_name,
    )
    session.add(patient)
    await session.flush()
    await session.refresh(patient)
    return UserRead.model_validate(patient)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    auth: Auth,
    session: DbSession,
) -> UserRead:
    """Get a user by ID, scoped to the authenticated org."""
    result = await session.execute(
        select(User).where(
            User.id == user_id,
            User.organization_id == auth.organization_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError(resource="User", resource_id=str(user_id))
    return UserRead.model_validate(user)
