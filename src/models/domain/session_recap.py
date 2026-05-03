"""Session recap Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HomeworkItem(BaseModel):
    """A homework/between-session task assigned in a session."""

    task: str = Field(..., description="What the patient committed to do")
    notes: str | None = Field(None, description="Optional context or acceptance criteria")


class SessionRecapRead(BaseModel):
    """LLM-generated recap of a therapy session, as returned to therapists."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Recap identifier")
    session_id: UUID = Field(..., description="Session this recap belongs to")
    brief: str = Field(..., description="2-3 sentence overview of the session")
    key_topics: list[str] = Field(..., description="Topics discussed")
    emotional_tone: str | None = Field(
        None, description="Overall emotional tenor (e.g., 'anxious, reflective')"
    )
    homework_assigned: list[HomeworkItem] = Field(
        default_factory=list, description="Between-session tasks committed to"
    )
    follow_ups: list[str] = Field(
        default_factory=list, description="Topics flagged for next session"
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Clinical risk indicators for therapist review (e.g., SI mentions)",
    )
    model_name: str = Field(..., description="LLM used to generate the recap")
    generated_at: datetime = Field(..., description="When the recap was generated")
    created_at: datetime = Field(..., description="Record creation time")
    updated_at: datetime = Field(..., description="Record update time")


class SessionRecapPayload(BaseModel):
    """Structured payload returned by the summarization LLM.

    The service parses the model's JSON response into this schema
    before persisting. Separated from the Read schema so DB fields
    (id, timestamps) aren't required during parsing.
    """

    brief: str = Field(..., max_length=2000)
    key_topics: list[str] = Field(default_factory=list, max_length=20)
    emotional_tone: str | None = Field(None, max_length=255)
    homework_assigned: list[HomeworkItem] = Field(default_factory=list, max_length=20)
    follow_ups: list[str] = Field(default_factory=list, max_length=20)
    risk_flags: list[str] = Field(default_factory=list, max_length=20)


class PatientRecapView(BaseModel):
    """Patient-facing subset of a session recap.

    Deliberately excludes therapist_notes, risk_flags, emotional_tone
    interpretation, and anything tied to the raw transcript. Built as a
    distinct schema (rather than Optional fields on SessionRecapRead) so
    that FastAPI's response_model serialization physically drops the
    clinician-only fields before they leave the server — a patient
    cannot see what isn't in this shape.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: UUID = Field(..., description="Session this recap belongs to")
    session_date: datetime = Field(..., description="When the session took place")
    brief: str = Field(..., description="2-3 sentence overview of the session")
    key_topics: list[str] = Field(
        default_factory=list, description="Topics discussed in plain language"
    )
    homework_assigned: list[HomeworkItem] = Field(
        default_factory=list, description="Between-session tasks committed to"
    )
    follow_ups: list[str] = Field(
        default_factory=list, description="Topics flagged for next session"
    )
    generated_at: datetime = Field(..., description="When the recap was generated")
