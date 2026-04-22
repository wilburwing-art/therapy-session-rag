"""Assessment service: records PHQ-9 / GAD-7 responses and computes scores."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError
from src.models.db.assessment import Assessment, AssessmentInstrument
from src.models.domain.assessment import (
    AssessmentCreate,
    AssessmentRead,
)
from src.models.domain.assessment import (
    AssessmentInstrument as DomainInstrument,
)

logger = logging.getLogger(__name__)


_INSTRUMENT_LENGTHS = {
    AssessmentInstrument.PHQ9: 9,
    AssessmentInstrument.GAD7: 7,
}


def _phq9_severity(score: int) -> str:
    # Standard clinical cutpoints for PHQ-9.
    if score <= 4:
        return "minimal"
    if score <= 9:
        return "mild"
    if score <= 14:
        return "moderate"
    if score <= 19:
        return "moderately_severe"
    return "severe"


def _gad7_severity(score: int) -> str:
    # Standard clinical cutpoints for GAD-7.
    if score <= 4:
        return "minimal"
    if score <= 9:
        return "mild"
    if score <= 14:
        return "moderate"
    return "severe"


def _severity_for(instrument: AssessmentInstrument, score: int) -> str:
    if instrument == AssessmentInstrument.PHQ9:
        return _phq9_severity(score)
    return _gad7_severity(score)


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        patient_id: uuid.UUID,
        administered_by_user_id: uuid.UUID,
        payload: AssessmentCreate,
    ) -> AssessmentRead:
        instrument = AssessmentInstrument(payload.instrument.value)
        expected_len = _INSTRUMENT_LENGTHS[instrument]
        if len(payload.responses) != expected_len:
            raise ValidationError(
                detail=(
                    f"{instrument.value.upper()} expects {expected_len} responses, "
                    f"got {len(payload.responses)}"
                ),
            )
        for idx, value in enumerate(payload.responses):
            if not 0 <= value <= 3:
                raise ValidationError(
                    detail=f"Response {idx} out of range (0-3): {value}",
                )

        total = sum(payload.responses)
        severity = _severity_for(instrument, total)
        now = datetime.now(UTC)

        assessment = Assessment(
            patient_id=patient_id,
            administered_by_user_id=administered_by_user_id,
            instrument=instrument,
            responses=payload.responses,
            total_score=total,
            severity=severity,
            notes=payload.notes,
            administered_at=now,
        )
        self.session.add(assessment)
        await self.session.flush()
        await self.session.refresh(assessment)
        logger.info(
            "Assessment recorded: patient=%s instrument=%s score=%d severity=%s",
            patient_id,
            instrument.value,
            total,
            severity,
        )
        return self._to_read(assessment)

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        instrument: DomainInstrument | None = None,
        limit: int = 50,
    ) -> list[AssessmentRead]:
        stmt = (
            select(Assessment)
            .where(Assessment.patient_id == patient_id)
            .order_by(Assessment.administered_at.desc())
            .limit(limit)
        )
        if instrument:
            stmt = stmt.where(
                Assessment.instrument == AssessmentInstrument(instrument.value)
            )
        result = await self.session.execute(stmt)
        return [self._to_read(a) for a in result.scalars().all()]

    @staticmethod
    def _to_read(a: Any) -> AssessmentRead:
        return AssessmentRead(
            id=a.id,
            patient_id=a.patient_id,
            administered_by_user_id=a.administered_by_user_id,
            instrument=DomainInstrument(a.instrument.value),
            responses=list(a.responses),
            total_score=a.total_score,
            severity=a.severity,
            notes=a.notes,
            administered_at=a.administered_at,
            created_at=a.created_at,
        )
