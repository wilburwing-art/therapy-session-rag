"""Unit tests for DataExportService.

Focuses on (a) the HIPAA export bundle shape for a fully populated
patient, (b) org-boundary enforcement, and (c) the tombstone event
written before the cascade delete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.db.assessment import Assessment, AssessmentInstrument
from src.models.db.consent import Consent, ConsentStatus, ConsentType
from src.models.db.conversation import Conversation, ConversationMessage, MessageRole
from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.patient_themes import PatientThemes
from src.models.db.session import Session as SessionRecording
from src.models.db.session import SessionStatus, SessionType
from src.models.db.session_recap import SessionRecap
from src.models.db.transcript import Transcript
from src.models.db.user import User, UserRole
from src.services.data_export_service import DataExportService


def _mock_patient(
    patient_id: uuid.UUID,
    org_id: uuid.UUID,
    email: str = "pt@example.com",
) -> MagicMock:
    u = MagicMock(spec=User)
    u.id = patient_id
    u.organization_id = org_id
    u.email = email
    u.full_name = "Pat Patient"
    u.role = UserRole.PATIENT
    u.email_verified_at = None
    u.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    u.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
    return u


def _mock_consent(patient_id: uuid.UUID, therapist_id: uuid.UUID) -> MagicMock:
    c = MagicMock(spec=Consent)
    c.id = uuid.uuid4()
    c.patient_id = patient_id
    c.therapist_id = therapist_id
    c.consent_type = ConsentType.RECORDING
    c.status = ConsentStatus.GRANTED
    c.granted_at = datetime(2026, 2, 5, tzinfo=UTC)
    c.revoked_at = None
    c.ip_address = "1.2.3.4"
    c.user_agent = "Mozilla/5.0"
    c.consent_metadata = {"note": "verbal + electronic"}
    return c


def _mock_session(patient_id: uuid.UUID, therapist_id: uuid.UUID) -> MagicMock:
    s = MagicMock(spec=SessionRecording)
    s.id = uuid.uuid4()
    s.patient_id = patient_id
    s.therapist_id = therapist_id
    s.consent_id = uuid.uuid4()
    s.session_date = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    s.status = SessionStatus.READY
    s.session_type = SessionType.UPLOAD
    s.recording_duration_seconds = 3000
    s.error_message = None
    s.session_metadata = {"source": "upload"}
    s.created_at = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    s.updated_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    return s


def _mock_recap(session_id: uuid.UUID) -> MagicMock:
    r = MagicMock(spec=SessionRecap)
    r.id = uuid.uuid4()
    r.session_id = session_id
    r.brief = "Short brief."
    r.key_topics = ["anxiety"]
    r.emotional_tone = "neutral"
    r.homework_assigned = [{"task": "breathing"}]
    r.follow_ups = ["check on sleep"]
    r.risk_flags = []
    r.model_name = "claude-sonnet-4"
    r.generated_at = datetime(2026, 3, 1, 13, 0, tzinfo=UTC)
    return r


def _mock_transcript(session_id: uuid.UUID) -> MagicMock:
    t = MagicMock(spec=Transcript)
    t.id = uuid.uuid4()
    t.session_id = session_id
    t.full_text = "Hello therapist. Hi patient."
    t.segments = [{"speaker": "A", "text": "Hello"}]
    t.word_count = 5
    t.duration_seconds = 120.0
    t.language = "en"
    t.confidence = 0.95
    t.transcript_metadata = {"model": "deepgram"}
    return t


def _mock_themes(patient_id: uuid.UUID) -> MagicMock:
    th = MagicMock(spec=PatientThemes)
    th.id = uuid.uuid4()
    th.patient_id = patient_id
    th.recurring_topics = [{"topic": "work-stress", "session_count": 2}]
    th.emotional_patterns = []
    th.coping_strategies = []
    th.progress_indicators = ["better sleep"]
    th.ongoing_concerns = []
    th.source_session_count = 2
    th.model_name = "claude-sonnet-4"
    th.generated_at = datetime(2026, 4, 1, tzinfo=UTC)
    return th


def _mock_conversation(patient_id: uuid.UUID) -> MagicMock:
    c = MagicMock(spec=Conversation)
    c.id = uuid.uuid4()
    c.patient_id = patient_id
    c.title = "First chat"
    c.message_count = 2
    c.created_at = datetime(2026, 3, 2, tzinfo=UTC)
    c.updated_at = datetime(2026, 3, 2, tzinfo=UTC)
    return c


def _mock_message(conversation_id: uuid.UUID, seq: int, role: MessageRole) -> MagicMock:
    m = MagicMock(spec=ConversationMessage)
    m.id = uuid.uuid4()
    m.conversation_id = conversation_id
    m.role = role
    m.content = f"msg {seq}"
    m.sequence_number = seq
    m.sources = None
    m.created_at = datetime(2026, 3, 2, tzinfo=UTC)
    return m


def _mock_assessment(patient_id: uuid.UUID) -> MagicMock:
    a = MagicMock(spec=Assessment)
    a.id = uuid.uuid4()
    a.patient_id = patient_id
    a.administered_by_user_id = uuid.uuid4()
    a.instrument = AssessmentInstrument.PHQ9
    a.responses = [1, 1, 2, 1, 1, 1, 1, 1, 1]
    a.total_score = 10
    a.severity = "moderate"
    a.notes = None
    a.administered_at = datetime(2026, 3, 5, tzinfo=UTC)
    return a


def _scalar_one_or_none(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(items: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> DataExportService:
    return DataExportService(mock_session)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def patient_id() -> uuid.UUID:
    return uuid.uuid4()


class TestExportPatient:
    async def test_full_bundle_shape(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        therapist_id = uuid.uuid4()
        patient = _mock_patient(patient_id, org_id)
        consent = _mock_consent(patient_id, therapist_id)
        sess = _mock_session(patient_id, therapist_id)
        recap = _mock_recap(sess.id)
        transcript = _mock_transcript(sess.id)
        themes = _mock_themes(patient_id)
        convo = _mock_conversation(patient_id)
        msg1 = _mock_message(convo.id, 0, MessageRole.USER)
        msg2 = _mock_message(convo.id, 1, MessageRole.ASSISTANT)
        assessment = _mock_assessment(patient_id)

        mock_session.execute.side_effect = [
            _scalar_one_or_none(patient),        # load patient
            _scalars_all([consent]),             # consents
            _scalars_all([sess]),                # sessions
            _scalars_all([recap]),               # recaps
            _scalars_all([transcript]),          # transcripts
            _scalar_one_or_none(themes),         # themes
            _scalars_all([convo]),               # conversations
            _scalars_all([msg1, msg2]),          # messages
            _scalars_all([assessment]),          # assessments
        ]

        bundle = await service.export_patient(patient_id, org_id)

        assert bundle["patient"]["id"] == str(patient_id)
        assert bundle["patient"]["email"] == "pt@example.com"
        assert len(bundle["consents"]) == 1
        assert bundle["consents"][0]["consent_type"] == "recording"
        assert len(bundle["sessions"]) == 1
        assert bundle["sessions"][0]["status"] == "ready"
        assert len(bundle["recaps"]) == 1
        assert bundle["recaps"][0]["brief"] == "Short brief."
        assert len(bundle["transcripts"]) == 1
        assert bundle["transcripts"][0]["full_text"] == "Hello therapist. Hi patient."
        assert bundle["themes"] is not None
        assert bundle["themes"]["source_session_count"] == 2
        assert len(bundle["conversations"]) == 1
        assert len(bundle["conversations"][0]["messages"]) == 2
        assert bundle["conversations"][0]["messages"][0]["role"] == "user"
        assert len(bundle["assessments"]) == 1
        assert bundle["assessments"][0]["instrument"] == "phq9"
        assert "exported_at" in bundle

    async def test_export_patient_without_sessions(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        patient = _mock_patient(patient_id, org_id)

        mock_session.execute.side_effect = [
            _scalar_one_or_none(patient),
            _scalars_all([]),       # consents
            _scalars_all([]),       # sessions
            _scalar_one_or_none(None),  # themes
            _scalars_all([]),       # conversations
            _scalars_all([]),       # assessments
        ]

        bundle = await service.export_patient(patient_id, org_id)

        assert bundle["sessions"] == []
        assert bundle["recaps"] == []
        assert bundle["transcripts"] == []
        assert bundle["themes"] is None
        assert bundle["conversations"] == []
        assert bundle["assessments"] == []

    async def test_export_patient_not_found(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute.return_value = _scalar_one_or_none(None)

        with pytest.raises(NotFoundError):
            await service.export_patient(uuid.uuid4(), org_id)

    async def test_export_wrong_org_forbidden(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Patient belongs to a different org than the caller."""
        wrong_org = uuid.uuid4()
        other_org = uuid.uuid4()
        patient = _mock_patient(patient_id, wrong_org)
        mock_session.execute.return_value = _scalar_one_or_none(patient)

        with pytest.raises(ForbiddenError):
            await service.export_patient(patient_id, other_org)

    async def test_export_rejects_non_patient_role(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        """Passing a therapist id as a 'patient' id is rejected with 404."""
        therapist_row = MagicMock(spec=User)
        therapist_row.id = patient_id
        therapist_row.organization_id = org_id
        therapist_row.role = UserRole.THERAPIST

        mock_session.execute.return_value = _scalar_one_or_none(therapist_row)

        with pytest.raises(NotFoundError):
            await service.export_patient(patient_id, org_id)


class TestDeletePatient:
    async def test_delete_writes_tombstone_then_deletes(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> None:
        therapist_id = uuid.uuid4()
        patient = _mock_patient(patient_id, org_id)

        session_ids = [uuid.uuid4(), uuid.uuid4()]
        transcript_ids = [uuid.uuid4(), uuid.uuid4()]
        conv_ids = [uuid.uuid4()]

        mock_session.execute.side_effect = [
            _scalar_one_or_none(patient),      # patient load
            _scalars_all(session_ids),         # session ids
            _scalars_all(transcript_ids),      # transcript ids
            _scalars_all(conv_ids),            # conversation ids
        ]
        mock_session.delete = AsyncMock()
        # add() is a synchronous attribute on AsyncMock; we inspect .call_args
        added: list[object] = []
        mock_session.add = MagicMock(side_effect=added.append)

        result = await service.delete_patient(
            patient_id=patient_id,
            org_id=org_id,
            therapist_id=therapist_id,
        )

        assert result["patient_id"] == str(patient_id)
        assert result["session_count_deleted"] == 2
        assert result["transcript_count_deleted"] == 2
        assert result["conversation_count_deleted"] == 1
        assert "deleted_at" in result

        # Tombstone must have been recorded before the delete.
        assert len(added) == 1
        tombstone = added[0]
        assert isinstance(tombstone, AnalyticsEvent)
        assert tombstone.event_name == "patient.data_deleted"
        assert tombstone.event_category == EventCategory.SYSTEM
        assert tombstone.organization_id == org_id
        assert tombstone.actor_id == therapist_id
        assert tombstone.properties is not None
        assert tombstone.properties["patient_id"] == str(patient_id)
        assert tombstone.properties["session_count_deleted"] == 2

        mock_session.delete.assert_awaited_once_with(patient)

    async def test_delete_rejects_cross_org(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        patient_id: uuid.UUID,
    ) -> None:
        patient = _mock_patient(patient_id, uuid.uuid4())
        mock_session.execute.return_value = _scalar_one_or_none(patient)

        with pytest.raises(ForbiddenError):
            await service.delete_patient(
                patient_id=patient_id,
                org_id=uuid.uuid4(),
                therapist_id=uuid.uuid4(),
            )

    async def test_delete_missing_patient_raises(
        self,
        service: DataExportService,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute.return_value = _scalar_one_or_none(None)

        with pytest.raises(NotFoundError):
            await service.delete_patient(
                patient_id=uuid.uuid4(),
                org_id=org_id,
                therapist_id=uuid.uuid4(),
            )
