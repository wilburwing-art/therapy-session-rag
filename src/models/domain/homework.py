"""Homework item Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HomeworkItemRead(BaseModel):
    """A between-session task assigned to a patient, as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Homework item identifier")
    session_id: UUID = Field(..., description="Session the task was assigned in")
    patient_id: UUID = Field(..., description="Patient the task is assigned to")
    task: str = Field(..., description="What the patient committed to do")
    notes: str | None = Field(None, description="Optional clinical context or acceptance criteria")
    completed: bool = Field(..., description="Whether the patient has marked the task done")
    completed_at: datetime | None = Field(None, description="Timestamp of completion, if completed")
    created_at: datetime = Field(..., description="When the task was recorded")
    updated_at: datetime = Field(..., description="Last update timestamp")


class HomeworkItemToggle(BaseModel):
    """Body for PATCH /homework/{id} to flip completion state."""

    completed: bool = Field(..., description="New completion state")
