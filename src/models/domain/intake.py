"""Intake form, invitation, and response Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class IntakeQuestionKind(StrEnum):
    """Accepted question input kinds."""

    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    SCALE = "scale"
    DATE = "date"


class IntakeFormStatusOut(StrEnum):
    """Form lifecycle mirrored from the DB enum."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class IntakeInvitationStatusOut(StrEnum):
    """Invitation lifecycle mirrored from the DB enum."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class IntakeQuestion(BaseModel):
    """A single question embedded in an intake form."""

    id: str = Field(..., min_length=1, max_length=64)
    prompt: str = Field(..., min_length=1, max_length=2048)
    kind: IntakeQuestionKind
    required: bool = True
    choices: list[str] | None = None
    help_text: str | None = Field(default=None, max_length=1024)


class IntakeFormCreate(BaseModel):
    """Request body for creating an intake form."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    questions: list[IntakeQuestion] = Field(default_factory=list)


class IntakeFormUpdate(BaseModel):
    """Request body for editing an intake form."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    status: IntakeFormStatusOut | None = None
    questions: list[IntakeQuestion] | None = None


class IntakeFormRead(BaseModel):
    """Intake form surfaced to therapists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    name: str
    description: str | None
    status: IntakeFormStatusOut
    questions: list[IntakeQuestion]
    created_at: datetime
    updated_at: datetime


class IntakeInvitationCreate(BaseModel):
    """Request body for sending an intake invitation to a prospective patient."""

    form_id: UUID
    patient_email: EmailStr
    patient_name: str | None = Field(default=None, max_length=255)


class IntakeInvitationCreateResponse(BaseModel):
    """Response returned when an invitation is issued.

    The raw token is returned once so the therapist can copy the
    complete intake URL if email delivery fails.
    """

    id: UUID
    form_id: UUID
    patient_email: EmailStr
    patient_name: str | None
    token: str = Field(
        ...,
        description=(
            "Raw intake token. Include as `?t={token}` in the intake URL "
            "if you need to share the invitation manually."
        ),
    )
    expires_at: datetime
    status: IntakeInvitationStatusOut


class IntakeInvitationRead(BaseModel):
    """Invitation surfaced on the patient detail page."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    form_id: UUID
    invited_by_user_id: UUID
    patient_email: EmailStr
    patient_name: str | None
    status: IntakeInvitationStatusOut
    expires_at: datetime
    submitted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class IntakeInvitationPublic(BaseModel):
    """Shape returned to the unauthenticated patient redeeming a token.

    Exposes only the fields needed to render the form — never leaks the
    therapist's identity or internal IDs beyond those required.
    """

    form_id: UUID
    practice_name: str
    patient_name: str | None
    questions: list[IntakeQuestion]
    expires_at: datetime


class IntakeSubmission(BaseModel):
    """Public request body for submitting intake answers.

    ``answers`` is a map of ``question_id -> answer``. Answer types are
    validated against the referenced form's questions in the service
    layer (strings for text, list[str] for multi_choice, etc.).
    """

    token: str = Field(..., min_length=8)
    answers: dict[str, Any] = Field(default_factory=dict)


class IntakeResponseRead(BaseModel):
    """Submitted intake response surfaced to therapists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invitation_id: UUID
    form_id: UUID
    organization_id: UUID
    answers: dict[str, Any]
    submitted_at: datetime


class IntakeContext(BaseModel):
    """Rendered intake context passed into recap generation.

    Compact text summary of a patient's intake responses suitable for
    prepending to the recap prompt.
    """

    patient_email: EmailStr
    rendered: str
