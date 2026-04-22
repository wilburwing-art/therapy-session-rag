"""Tests for AssessmentService scoring and validation."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ValidationError
from src.models.db.assessment import Assessment, AssessmentInstrument
from src.models.domain.assessment import (
    AssessmentCreate,
)
from src.models.domain.assessment import (
    AssessmentInstrument as DomainInstrument,
)
from src.services.assessment_service import AssessmentService


@pytest.fixture
def service() -> AssessmentService:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    # Simulate the DB assigning defaults on insert so Pydantic can
    # validate the ORM object.
    async def _refresh(obj: object) -> None:
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()  # type: ignore[attr-defined]
        now = datetime.now(UTC)
        obj.created_at = now  # type: ignore[attr-defined]
        obj.updated_at = now  # type: ignore[attr-defined]
    db.refresh = AsyncMock(side_effect=_refresh)
    db.execute = AsyncMock()
    return AssessmentService(db)


def _patient() -> uuid.UUID:
    return uuid.uuid4()


def _make_row(instrument: AssessmentInstrument, score: int, severity: str) -> Assessment:
    row = MagicMock(spec=Assessment)
    row.id = uuid.uuid4()
    row.patient_id = uuid.uuid4()
    row.administered_by_user_id = uuid.uuid4()
    row.instrument = instrument
    row.responses = [0, 0, 0, 0, 0, 0, 0]
    row.total_score = score
    row.severity = severity
    row.notes = None
    row.administered_at = datetime.now(UTC)
    row.created_at = datetime.now(UTC)
    return row


@pytest.mark.asyncio
async def test_phq9_validates_length(service: AssessmentService) -> None:
    with pytest.raises(ValidationError):
        await service.record(
            patient_id=_patient(),
            administered_by_user_id=uuid.uuid4(),
            payload=AssessmentCreate(
                instrument=DomainInstrument.PHQ9,
                responses=[0, 0, 0, 0, 0, 0, 0],  # only 7, PHQ-9 needs 9
            ),
        )


@pytest.mark.asyncio
async def test_gad7_validates_length(service: AssessmentService) -> None:
    with pytest.raises(ValidationError):
        await service.record(
            patient_id=_patient(),
            administered_by_user_id=uuid.uuid4(),
            payload=AssessmentCreate(
                instrument=DomainInstrument.GAD7,
                responses=[0, 0, 0, 0, 0, 0, 0, 0],  # 8, GAD-7 needs 7
            ),
        )


@pytest.mark.asyncio
async def test_rejects_out_of_range_responses(
    service: AssessmentService,
) -> None:
    with pytest.raises(ValidationError):
        await service.record(
            patient_id=_patient(),
            administered_by_user_id=uuid.uuid4(),
            payload=AssessmentCreate(
                instrument=DomainInstrument.GAD7,
                responses=[0, 0, 0, 5, 0, 0, 0],
            ),
        )


@pytest.mark.asyncio
async def test_phq9_scoring_severity_bands(service: AssessmentService) -> None:
    cases = [
        ([0] * 9, "minimal"),  # 0
        ([1, 1, 1, 1, 1, 0, 0, 0, 0], "mild"),  # 5
        ([1] * 9, "mild"),  # 9
        ([1, 1, 1, 2, 2, 2, 1, 0, 0], "moderate"),  # 10
        ([2, 2, 2, 2, 2, 2, 2, 1, 0], "moderately_severe"),  # 15
        ([3] * 9, "severe"),  # 27
    ]
    patient_id = _patient()
    for responses, expected_severity in cases:
        expected_total = sum(responses)
        result = await service.record(
            patient_id=patient_id,
            administered_by_user_id=uuid.uuid4(),
            payload=AssessmentCreate(
                instrument=DomainInstrument.PHQ9,
                responses=responses,
            ),
        )
        assert result.total_score == expected_total
        assert result.severity == expected_severity


@pytest.mark.asyncio
async def test_gad7_scoring_severity_bands(service: AssessmentService) -> None:
    cases = [
        ([0] * 7, "minimal"),  # 0
        ([1, 1, 1, 1, 0, 0, 0], "minimal"),  # 4
        ([1, 1, 1, 1, 1, 0, 0], "mild"),  # 5
        ([2, 2, 2, 2, 2, 0, 0], "moderate"),  # 10
        ([3, 3, 3, 3, 3, 0, 0], "severe"),  # 15
    ]
    patient_id = _patient()
    for responses, expected_severity in cases:
        result = await service.record(
            patient_id=patient_id,
            administered_by_user_id=uuid.uuid4(),
            payload=AssessmentCreate(
                instrument=DomainInstrument.GAD7,
                responses=responses,
            ),
        )
        assert result.severity == expected_severity
