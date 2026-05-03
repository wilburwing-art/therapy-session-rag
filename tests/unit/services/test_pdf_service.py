"""Unit tests for :class:`PdfService`.

The service reaches into the DB session and three repositories. Tests
use MagicMocks for every ORM row; the real interaction with ReportLab
is exercised end-to-end so a regression in the flowable builders shows
up as a rendering error rather than a silent bug.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.db.user import UserRole
from src.services.pdf_service import PdfService


def _mock_user(
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    *,
    role: UserRole = UserRole.PATIENT,
    full_name: str = "Alex Example",
    email: str = "alex@example.com",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.organization_id = organization_id
    user.role = role
    user.full_name = full_name
    user.email = email
    return user


def _mock_session(
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
    session_date: datetime | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = session_id
    s.patient_id = patient_id
    s.therapist_id = therapist_id
    s.session_date = session_date or datetime(2026, 4, 10, 14, 0, 0, tzinfo=UTC)
    s.status = MagicMock(value="ready")
    s.session_type = MagicMock(value="upload")
    s.recording_duration_seconds = 2700
    return s


def _mock_recap(session_id: uuid.UUID) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.session_id = session_id
    r.brief = "Patient discussed sleep and work stress."
    r.key_topics = ["sleep", "work stress", "family"]
    r.emotional_tone = "reflective, fatigued"
    r.homework_assigned = [{"task": "Journal nightly", "notes": "5 min"}]
    r.follow_ups = ["Revisit sleep hygiene plan"]
    r.risk_flags = []
    r.model_name = "claude-sonnet-4"
    r.generated_at = datetime(2026, 4, 11, 0, 0, 0, tzinfo=UTC)
    r.created_at = r.generated_at
    r.updated_at = r.generated_at
    return r


def _mock_themes(patient_id: uuid.UUID) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.patient_id = patient_id
    t.recurring_topics = [
        {"topic": "sleep", "session_count": 3, "summary": "Interrupted sleep midweek"},
    ]
    t.emotional_patterns = [
        {"pattern": "anticipatory anxiety", "evidence": "spikes Sunday evenings"},
    ]
    t.coping_strategies = [
        {"strategy": "box breathing", "notes": "used during meetings"},
    ]
    t.progress_indicators = ["Sleep slightly improved"]
    t.ongoing_concerns = ["Caregiver stress"]
    t.source_session_count = 3
    t.model_name = "claude-sonnet-4"
    t.generated_at = datetime(2026, 4, 20, 0, 0, 0, tzinfo=UTC)
    t.created_at = t.generated_at
    t.updated_at = t.generated_at
    return t


def _mock_assessment(
    patient_id: uuid.UUID,
    *,
    instrument_value: str = "phq9",
    total_score: int = 12,
    severity: str = "moderate",
    administered_at: datetime | None = None,
) -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.patient_id = patient_id
    a.instrument = MagicMock(value=instrument_value)
    a.total_score = total_score
    a.severity = severity
    a.administered_at = administered_at or datetime(2026, 4, 15, 0, 0, 0, tzinfo=UTC)
    return a


def _mock_org(organization_id: uuid.UUID, name: str = "Maplewood Therapy") -> MagicMock:
    org = MagicMock()
    org.id = organization_id
    org.name = name
    return org


@pytest.fixture
def organization_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def therapist_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def service() -> PdfService:
    svc = PdfService(db_session=MagicMock())
    svc.session_repo = MagicMock()
    svc.recap_repo = MagicMock()
    svc.themes_repo = MagicMock()
    return svc


class TestRenderSessionRecapPdf:
    @pytest.mark.asyncio
    async def test_returns_pdf_bytes(
        self,
        service: PdfService,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        service.session_repo.get_by_id = AsyncMock(
            return_value=_mock_session(session_id, patient_id, therapist_id)
        )
        service.recap_repo.get_by_session_id = AsyncMock(return_value=_mock_recap(session_id))

        patient_user = _mock_user(patient_id, organization_id, role=UserRole.PATIENT)
        therapist_user = _mock_user(
            therapist_id,
            organization_id,
            role=UserRole.THERAPIST,
            full_name="Dr. Therapist",
            email="therapist@example.com",
        )
        org_row = _mock_org(organization_id)

        # The service hits db_session.execute() for user + org lookups.
        # Return results in the order the service calls them: patient,
        # therapist (twice: in _load_session_in_org and _get_user for
        # recap flowables), then org. We side-effect to cover the exact
        # call sequence.
        db_results = iter(
            [
                _scalar_one(patient_user),
                _scalar_one(therapist_user),
                _scalar_one(patient_user),
                _scalar_one(therapist_user),
                _scalar_one(org_row),
            ]
        )
        service.db_session.execute = AsyncMock(side_effect=lambda *_a, **_kw: next(db_results))  # type: ignore[attr-defined]

        pdf_bytes = await service.render_session_recap_pdf(
            session_id=session_id,
            organization_id=organization_id,
        )

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 500

    @pytest.mark.asyncio
    async def test_raises_when_session_missing(
        self,
        service: PdfService,
        session_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        service.session_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await service.render_session_recap_pdf(
                session_id=session_id,
                organization_id=organization_id,
            )

    @pytest.mark.asyncio
    async def test_raises_forbidden_when_org_mismatch(
        self,
        service: PdfService,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        other_org = uuid.uuid4()
        service.session_repo.get_by_id = AsyncMock(
            return_value=_mock_session(session_id, patient_id, therapist_id)
        )
        patient_user = _mock_user(patient_id, other_org, role=UserRole.PATIENT)
        therapist_user = _mock_user(therapist_id, other_org, role=UserRole.THERAPIST)
        db_results = iter([_scalar_one(patient_user), _scalar_one(therapist_user)])
        service.db_session.execute = AsyncMock(side_effect=lambda *_a, **_kw: next(db_results))  # type: ignore[attr-defined]

        with pytest.raises(ForbiddenError):
            await service.render_session_recap_pdf(
                session_id=session_id,
                organization_id=organization_id,
            )

    @pytest.mark.asyncio
    async def test_raises_when_recap_missing(
        self,
        service: PdfService,
        session_id: uuid.UUID,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        service.session_repo.get_by_id = AsyncMock(
            return_value=_mock_session(session_id, patient_id, therapist_id)
        )
        service.recap_repo.get_by_session_id = AsyncMock(return_value=None)

        patient_user = _mock_user(patient_id, organization_id, role=UserRole.PATIENT)
        therapist_user = _mock_user(therapist_id, organization_id, role=UserRole.THERAPIST)
        db_results = iter([_scalar_one(patient_user), _scalar_one(therapist_user)])
        service.db_session.execute = AsyncMock(side_effect=lambda *_a, **_kw: next(db_results))  # type: ignore[attr-defined]

        with pytest.raises(NotFoundError):
            await service.render_session_recap_pdf(
                session_id=session_id,
                organization_id=organization_id,
            )


class TestRenderThemesPdf:
    @pytest.mark.asyncio
    async def test_returns_pdf_bytes(
        self,
        service: PdfService,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        patient_user = _mock_user(patient_id, organization_id)
        org_row = _mock_org(organization_id)
        db_results = iter([_scalar_one(patient_user), _scalar_one(org_row)])
        service.db_session.execute = AsyncMock(side_effect=lambda *_a, **_kw: next(db_results))  # type: ignore[attr-defined]

        service.themes_repo.get_by_patient_id = AsyncMock(return_value=_mock_themes(patient_id))

        pdf_bytes = await service.render_themes_pdf(
            patient_id=patient_id,
            organization_id=organization_id,
        )

        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_raises_forbidden_when_patient_in_other_org(
        self,
        service: PdfService,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        other_org = uuid.uuid4()
        patient_user = _mock_user(patient_id, other_org)
        service.db_session.execute = AsyncMock(return_value=_scalar_one(patient_user))

        with pytest.raises(ForbiddenError):
            await service.render_themes_pdf(
                patient_id=patient_id,
                organization_id=organization_id,
            )

    @pytest.mark.asyncio
    async def test_raises_when_no_themes(
        self,
        service: PdfService,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        patient_user = _mock_user(patient_id, organization_id)
        service.db_session.execute = AsyncMock(return_value=_scalar_one(patient_user))
        service.themes_repo.get_by_patient_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await service.render_themes_pdf(
                patient_id=patient_id,
                organization_id=organization_id,
            )


class TestRenderPatientRecordPdf:
    @pytest.mark.asyncio
    async def test_returns_pdf_bytes_with_full_data(
        self,
        service: PdfService,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        patient_user = _mock_user(patient_id, organization_id)
        org_row = _mock_org(organization_id)

        s1 = _mock_session(uuid.uuid4(), patient_id, therapist_id)
        s2 = _mock_session(
            uuid.uuid4(),
            patient_id,
            therapist_id,
            session_date=datetime(2026, 4, 17, 15, 0, 0, tzinfo=UTC),
        )

        recap_1 = _mock_recap(s1.id)
        recap_2 = _mock_recap(s2.id)

        assessment_1 = _mock_assessment(
            patient_id,
            instrument_value="phq9",
            total_score=15,
            severity="moderately_severe",
        )
        assessment_2 = _mock_assessment(
            patient_id,
            instrument_value="gad7",
            total_score=7,
            severity="mild",
        )

        # db_session.execute is called in this order:
        # 1. _load_patient_in_org -> patient
        # 2. _get_practice_name -> org
        # 3. _list_sessions_for_patient -> [s1, s2]
        # 4. _recaps_by_session -> [recap1, recap2]
        # 5. _list_assessments_for_patient -> [a1, a2]
        db_results = iter(
            [
                _scalar_one(patient_user),
                _scalar_one(org_row),
                _scalars_all([s1, s2]),
                _scalars_all([recap_1, recap_2]),
                _scalars_all([assessment_1, assessment_2]),
            ]
        )
        service.db_session.execute = AsyncMock(side_effect=lambda *_a, **_kw: next(db_results))  # type: ignore[attr-defined]

        service.themes_repo.get_by_patient_id = AsyncMock(return_value=_mock_themes(patient_id))

        pdf_bytes = await service.render_patient_record_pdf(
            patient_id=patient_id,
            organization_id=organization_id,
        )

        assert pdf_bytes.startswith(b"%PDF")
        # A multi-page doc should be larger than the single-page recap PDF.
        assert len(pdf_bytes) > 1500

    @pytest.mark.asyncio
    async def test_handles_patient_with_no_sessions(
        self,
        service: PdfService,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        patient_user = _mock_user(patient_id, organization_id)
        org_row = _mock_org(organization_id)

        db_results = iter(
            [
                _scalar_one(patient_user),
                _scalar_one(org_row),
                _scalars_all([]),  # no sessions
                _scalars_all([]),  # no assessments
            ]
        )
        service.db_session.execute = AsyncMock(side_effect=lambda *_a, **_kw: next(db_results))  # type: ignore[attr-defined]

        service.themes_repo.get_by_patient_id = AsyncMock(return_value=None)

        pdf_bytes = await service.render_patient_record_pdf(
            patient_id=patient_id,
            organization_id=organization_id,
        )
        assert pdf_bytes.startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_raises_forbidden_when_org_mismatch(
        self,
        service: PdfService,
        patient_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> None:
        other_org = uuid.uuid4()
        patient_user = _mock_user(patient_id, other_org)
        service.db_session.execute = AsyncMock(return_value=_scalar_one(patient_user))

        with pytest.raises(ForbiddenError):
            await service.render_patient_record_pdf(
                patient_id=patient_id,
                organization_id=organization_id,
            )


def _scalar_one(row: object | None) -> MagicMock:
    """Build a fake execute() result whose scalar_one_or_none returns *row*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    return result


def _scalars_all(rows: list[object]) -> MagicMock:
    """Build a fake execute() result whose scalars().all() returns *rows*."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result
