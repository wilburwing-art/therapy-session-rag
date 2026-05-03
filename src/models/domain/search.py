"""Search domain schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchSource(StrEnum):
    """Which table a search hit came from."""

    TRANSCRIPT = "transcript"
    RECAP = "recap"
    NOTES = "notes"


class SearchHit(BaseModel):
    """A single full-text search hit across therapy sessions.

    Returned by GET /api/v1/search. The ``snippet`` field contains
    Postgres ``ts_headline`` output with ``<mark>`` tags wrapping the
    matched terms; the frontend is responsible for sanitizing and
    rendering those tags.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: UUID = Field(..., description="ID of the session the hit belongs to")
    patient_id: UUID = Field(..., description="ID of the patient on that session")
    patient_name: str | None = Field(None, description="Display name of the patient, if set")
    session_date: datetime = Field(..., description="Date and time of the session")
    source: SearchSource = Field(
        ...,
        description="Which document contributed the match (transcript, recap, or notes)",
    )
    snippet: str = Field(
        ...,
        description="Highlighted excerpt from the matched document with <mark> tags",
    )
    rank: float = Field(..., description="Postgres ts_rank_cd score; higher is better")
