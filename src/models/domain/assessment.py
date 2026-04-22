"""Assessment Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssessmentInstrument(StrEnum):
    PHQ9 = "phq9"
    GAD7 = "gad7"


class AssessmentCreate(BaseModel):
    """Submit a completed assessment.

    Response values are 0-3 (both PHQ-9 and GAD-7 use the same Likert
    scale); length is validated against the instrument on the server.
    """

    instrument: AssessmentInstrument
    responses: list[int] = Field(..., min_length=7, max_length=9)
    notes: str | None = Field(None, max_length=2048)


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    administered_by_user_id: UUID | None = None
    instrument: AssessmentInstrument
    responses: list[int]
    total_score: int
    severity: str | None
    notes: str | None
    administered_at: datetime
    created_at: datetime
