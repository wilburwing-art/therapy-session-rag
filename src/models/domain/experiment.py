"""Experiment Pydantic schemas for A/B testing."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExperimentStatus(StrEnum):
    """Status of an experiment."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class ExperimentCreate(BaseModel):
    """Schema for creating an experiment."""

    name: str = Field(..., max_length=255, description="Unique experiment name")
    description: str | None = Field(None, description="Experiment description")
    variants: dict[str, Any] = Field(
        ...,
        description="Variant definitions (e.g. {'control': {}, 'treatment': {'top_k': 10}})",
    )
    targeting_rules: dict[str, Any] | None = Field(
        None, description="Targeting rules for subject eligibility"
    )
    traffic_percentage: int = Field(
        100, ge=1, le=100, description="Percentage of traffic to include"
    )


class ExperimentRead(BaseModel):
    """Schema for reading an experiment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: ExperimentStatus
    organization_id: UUID
    variants: dict[str, Any]
    targeting_rules: dict[str, Any] | None
    traffic_percentage: int
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExperimentUpdate(BaseModel):
    """Schema for updating an experiment."""

    description: str | None = None
    variants: dict[str, Any] | None = None
    targeting_rules: dict[str, Any] | None = None
    traffic_percentage: int | None = Field(None, ge=1, le=100)


class AssignmentRead(BaseModel):
    """Schema for reading an experiment assignment."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    experiment_id: UUID
    subject_id: UUID
    variant: str
    assigned_at: datetime


class MetricRecord(BaseModel):
    """Schema for recording a metric observation."""

    metric_name: str = Field(..., max_length=255)
    metric_value: float
    subject_id: UUID


class ExperimentResults(BaseModel):
    """Statistical analysis results for an experiment."""

    experiment_id: UUID
    experiment_name: str
    status: ExperimentStatus
    variant_stats: dict[str, "VariantStats"]
    is_significant: bool
    p_value: float | None
    confidence_level: float


class VariantStats(BaseModel):
    """Statistics for a single variant."""

    variant_name: str
    subject_count: int
    metric_mean: float
    metric_std: float
    metric_min: float
    metric_max: float


# Rebuild to resolve forward reference
ExperimentResults.model_rebuild()
