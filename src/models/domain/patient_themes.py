"""Patient themes Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecurringTopic(BaseModel):
    """A topic that appears across multiple sessions."""

    topic: str = Field(..., description="Short name of the topic")
    session_count: int = Field(..., description="Number of sessions in which this appeared")
    summary: str | None = Field(None, description="One-sentence characterization")


class EmotionalPattern(BaseModel):
    """A recurring emotional pattern observed across sessions."""

    pattern: str = Field(..., description="Short pattern name")
    evidence: str | None = Field(None, description="Paraphrased evidence or quote")


class CopingStrategy(BaseModel):
    """A coping strategy the patient has discussed or tried."""

    strategy: str = Field(..., description="Strategy name")
    notes: str | None = Field(None, description="Outcome, commitment level, or context")


class PatientThemesPayload(BaseModel):
    """Structured LLM output for cross-session theme synthesis."""

    recurring_topics: list[RecurringTopic] = Field(default_factory=list, max_length=15)
    emotional_patterns: list[EmotionalPattern] = Field(default_factory=list, max_length=15)
    coping_strategies: list[CopingStrategy] = Field(default_factory=list, max_length=15)
    progress_indicators: list[str] = Field(default_factory=list, max_length=15)
    ongoing_concerns: list[str] = Field(default_factory=list, max_length=15)


class PatientThemesRead(BaseModel):
    """Themes document returned to the therapist dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_id: UUID
    recurring_topics: list[RecurringTopic]
    emotional_patterns: list[EmotionalPattern]
    coping_strategies: list[CopingStrategy]
    progress_indicators: list[str]
    ongoing_concerns: list[str]
    source_session_count: int = Field(
        ..., description="Number of session recaps used to synthesize these themes"
    )
    model_name: str
    generated_at: datetime
    created_at: datetime
    updated_at: datetime
