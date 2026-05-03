"""Users API endpoints."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from src.api.v1.dependencies import Auth, CurrentTherapist
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


# --- reminders-engineer: notification preferences endpoint (END anchor) ---

_ALLOWED_CHANNELS = {"sms", "email", "in_app"}
_ALLOWED_KINDS = {
    "homework_due",
    "session_upcoming",
    "intake_pending",
    "assessment_due",
}


class NotificationPreferencesUpdate(BaseModel):
    """Partial update of a user's notification preferences.

    All fields are optional — any omitted field keeps its existing
    value. Empty collections explicitly clear the corresponding
    preference.
    """

    channels: dict[str, bool] | None = Field(
        default=None,
        description=(
            "Per-channel opt-in flags. Valid keys: sms, email, in_app. "
            "Unknown keys return 422."
        ),
    )
    kinds: dict[str, bool] | None = Field(
        default=None,
        description=(
            "Per-reminder-kind opt-in flags. Valid keys: homework_due, "
            "session_upcoming, intake_pending, assessment_due."
        ),
    )
    phone_number: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Destination phone number in E.164. Pass an empty string to "
            "clear an existing number."
        ),
    )
    quiet_hours_start: int | None = Field(
        default=None,
        ge=0,
        le=23,
        description="Hour of day (0-23, user local) when quiet hours begin.",
    )
    quiet_hours_end: int | None = Field(
        default=None,
        ge=0,
        le=23,
        description="Hour of day (0-23, user local) when quiet hours end.",
    )
    timezone: str | None = Field(
        default=None,
        max_length=64,
        description="IANA timezone used to interpret quiet hours.",
    )


class NotificationPreferencesRead(BaseModel):
    """Current notification preferences for the authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    notification_preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="Current preferences object.",
    )


def _merge_notification_preferences(
    current: dict[str, Any],
    update: NotificationPreferencesUpdate,
) -> dict[str, Any]:
    """Shallow-merge an update into the current preferences.

    Raises ValueError if the update contains unknown channel/kind keys.
    """
    merged: dict[str, Any] = dict(current)

    if update.channels is not None:
        unknown = set(update.channels) - _ALLOWED_CHANNELS
        if unknown:
            raise ValueError(f"Unknown channels: {sorted(unknown)}")
        channels_current = dict(merged.get("channels", {}))
        channels_current.update(update.channels)
        merged["channels"] = channels_current

    if update.kinds is not None:
        unknown = set(update.kinds) - _ALLOWED_KINDS
        if unknown:
            raise ValueError(f"Unknown reminder kinds: {sorted(unknown)}")
        kinds_current = dict(merged.get("kinds", {}))
        kinds_current.update(update.kinds)
        merged["kinds"] = kinds_current

    if update.phone_number is not None:
        # Empty string clears the number.
        merged["phone_number"] = update.phone_number or None

    if update.quiet_hours_start is not None:
        merged["quiet_hours_start"] = update.quiet_hours_start
    if update.quiet_hours_end is not None:
        merged["quiet_hours_end"] = update.quiet_hours_end
    if update.timezone is not None:
        merged["timezone"] = update.timezone

    return merged


@router.patch(
    "/me/notifications",
    response_model=NotificationPreferencesRead,
)
async def update_my_notification_preferences(
    payload: NotificationPreferencesUpdate,
    me: CurrentTherapist,
    session: DbSession,
) -> NotificationPreferencesRead:
    """Update the authenticated therapist's notification preferences.

    Accepts a partial update: any field omitted from the body is left
    untouched. Unknown channel or reminder-kind keys return 422.
    """
    try:
        merged = _merge_notification_preferences(
            dict(me.notification_preferences or {}),
            payload,
        )
    except ValueError as exc:
        raise ConflictError(detail=str(exc)) from exc

    # The therapist dependency returns a detached User; re-fetch for
    # the write path so SQLAlchemy tracks the mutation.
    bound = await session.get(User, me.id)
    if bound is None:
        raise NotFoundError(resource="User", resource_id=str(me.id))
    bound.notification_preferences = merged
    await session.flush()
    await session.refresh(bound)

    return NotificationPreferencesRead(
        notification_preferences=dict(bound.notification_preferences or {}),
    )


# --- end reminders-engineer notification preferences anchor ---
