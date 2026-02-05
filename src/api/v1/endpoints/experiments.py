"""Experiment API endpoints for A/B testing management."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.v1.dependencies import Auth
from src.core.database import DbSession
from src.models.db.experiment import ExperimentStatus
from src.models.domain.experiment import (
    ExperimentCreate,
    ExperimentRead,
    ExperimentResults,
    ExperimentUpdate,
    MetricRecord,
)
from src.services.experiment_service import ExperimentService, ExperimentServiceError

router = APIRouter()


def get_experiment_service(session: DbSession) -> ExperimentService:
    """Get experiment service instance."""
    return ExperimentService(session)


ExperimentSvc = Annotated[ExperimentService, Depends(get_experiment_service)]


@router.post("", response_model=ExperimentRead, status_code=201)
async def create_experiment(
    auth: Auth,
    service: ExperimentSvc,
    data: ExperimentCreate,
) -> ExperimentRead:
    """Create a new experiment."""
    try:
        return await service.create_experiment(data, auth.organization_id)
    except ExperimentServiceError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("", response_model=list[ExperimentRead])
async def list_experiments(
    auth: Auth,
    service: ExperimentSvc,
    status: ExperimentStatus | None = Query(None, description="Filter by status"),
) -> list[ExperimentRead]:
    """List experiments for the organization."""
    return await service.list_experiments(auth.organization_id, status=status)


@router.get("/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
) -> ExperimentRead:
    """Get experiment by ID."""
    result = await service.get_experiment(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return result


@router.patch("/{experiment_id}", response_model=ExperimentRead)
async def update_experiment(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
    data: ExperimentUpdate,
) -> ExperimentRead:
    """Update experiment settings (DRAFT only)."""
    try:
        return await service.update_experiment(experiment_id, data)
    except ExperimentServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{experiment_id}/start", response_model=ExperimentRead)
async def start_experiment(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
) -> ExperimentRead:
    """Start a DRAFT experiment."""
    try:
        return await service.start_experiment(experiment_id)
    except ExperimentServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{experiment_id}/stop", response_model=ExperimentRead)
async def stop_experiment(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
) -> ExperimentRead:
    """Stop a RUNNING experiment."""
    try:
        return await service.stop_experiment(experiment_id)
    except ExperimentServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{experiment_id}/assign/{subject_id}")
async def assign_subject(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
    subject_id: uuid.UUID,
) -> dict[str, str]:
    """Assign a subject to a variant."""
    try:
        variant = await service.assign_subject(experiment_id, subject_id)
        return {"variant": variant}
    except ExperimentServiceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{experiment_id}/metrics", status_code=201)
async def record_metric(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
    data: MetricRecord,
) -> dict[str, str]:
    """Record a metric observation for a subject."""
    await service.record_metric(
        experiment_id=experiment_id,
        subject_id=data.subject_id,
        metric_name=data.metric_name,
        metric_value=data.metric_value,
    )
    return {"status": "recorded"}


@router.get("/{experiment_id}/results", response_model=ExperimentResults)
async def get_results(
    _auth: Auth,
    service: ExperimentSvc,
    experiment_id: uuid.UUID,
    metric_name: str = Query(..., description="Metric name to analyze"),
    confidence_level: float = Query(0.95, ge=0.5, le=0.99, description="Confidence level"),
) -> ExperimentResults:
    """Get experiment results with statistical significance."""
    try:
        return await service.get_results(
            experiment_id=experiment_id,
            metric_name=metric_name,
            confidence_level=confidence_level,
        )
    except ExperimentServiceError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
