"""HIPAA patient-data rights service.

Right-to-access: bundle every piece of a patient's data into a single
structured dict, leaving out server-side vectors that aren't meaningful
to a human reader.

Right-to-deletion: write a tombstone audit event *before* cascading the
delete so the operator record of the deletion survives even though the
originating patient, sessions, and transcripts do not.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenError, NotFoundError
from src.models.db.assessment import Assessment
from src.models.db.consent import Consent
from src.models.db.conversation import Conversation, ConversationMessage
from src.models.db.event import AnalyticsEvent, EventCategory
from src.models.db.patient_themes import PatientThemes
from src.models.db.session import Session as SessionRecording
from src.models.db.session_recap import SessionRecap
from src.models.db.transcript import Transcript
from src.models.db.user import User, UserRole

logger = logging.getLogger(__name__)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


class DataExportService:
    """Export and delete patient data for HIPAA rights requests."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def export_patient(
        self,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Return a structured bundle of everything tied to a patient.

        The caller is expected to have already authenticated and to be
        authorized for this patient's organization; we re-check the
        patient's org membership defensively and raise on mismatch.
        """
        patient = await self._load_patient_in_org(patient_id, org_id)

        consents = list(
            (
                await self.db_session.execute(
                    select(Consent)
                    .where(Consent.patient_id == patient_id)
                    .order_by(Consent.granted_at.asc())
                )
            )
            .scalars()
            .all()
        )
        sessions = list(
            (
                await self.db_session.execute(
                    select(SessionRecording)
                    .where(SessionRecording.patient_id == patient_id)
                    .order_by(SessionRecording.session_date.asc())
                )
            )
            .scalars()
            .all()
        )
        session_ids = [s.id for s in sessions]

        recaps: list[SessionRecap] = []
        transcripts: list[Transcript] = []
        if session_ids:
            recap_rows = await self.db_session.execute(
                select(SessionRecap)
                .where(SessionRecap.session_id.in_(session_ids))
                .order_by(SessionRecap.generated_at.asc())
            )
            recaps = list(recap_rows.scalars().all())

            transcript_rows = await self.db_session.execute(
                select(Transcript).where(Transcript.session_id.in_(session_ids))
            )
            transcripts = list(transcript_rows.scalars().all())

        themes_row = await self.db_session.execute(
            select(PatientThemes).where(PatientThemes.patient_id == patient_id)
        )
        themes = themes_row.scalar_one_or_none()

        conversation_rows = await self.db_session.execute(
            select(Conversation)
            .where(Conversation.patient_id == patient_id)
            .order_by(Conversation.created_at.asc())
        )
        conversations = list(conversation_rows.scalars().all())
        conv_ids = [c.id for c in conversations]

        messages: list[ConversationMessage] = []
        if conv_ids:
            msg_rows = await self.db_session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id.in_(conv_ids))
                .order_by(
                    ConversationMessage.conversation_id,
                    ConversationMessage.sequence_number,
                )
            )
            messages = list(msg_rows.scalars().all())

        assessment_rows = await self.db_session.execute(
            select(Assessment)
            .where(Assessment.patient_id == patient_id)
            .order_by(Assessment.administered_at.asc())
        )
        assessments = list(assessment_rows.scalars().all())

        return {
            "exported_at": datetime.now(UTC).isoformat(),
            "patient": {
                "id": str(patient.id),
                "organization_id": str(patient.organization_id),
                "email": patient.email,
                "full_name": patient.full_name,
                "role": patient.role.value,
                "email_verified_at": _iso(patient.email_verified_at),
                "created_at": _iso(patient.created_at),
                "updated_at": _iso(patient.updated_at),
            },
            "consents": [
                {
                    "id": str(c.id),
                    "therapist_id": str(c.therapist_id),
                    "consent_type": c.consent_type.value,
                    "status": c.status.value,
                    "granted_at": _iso(c.granted_at),
                    "revoked_at": _iso(c.revoked_at),
                    "ip_address": c.ip_address,
                    "user_agent": c.user_agent,
                    "metadata": c.consent_metadata,
                }
                for c in consents
            ],
            "sessions": [
                {
                    "id": str(s.id),
                    "therapist_id": str(s.therapist_id),
                    "consent_id": str(s.consent_id),
                    "session_date": _iso(s.session_date),
                    "status": s.status.value,
                    "session_type": s.session_type.value,
                    "recording_duration_seconds": s.recording_duration_seconds,
                    "error_message": s.error_message,
                    "metadata": s.session_metadata,
                    "created_at": _iso(s.created_at),
                    "updated_at": _iso(s.updated_at),
                }
                for s in sessions
            ],
            "recaps": [
                {
                    "id": str(r.id),
                    "session_id": str(r.session_id),
                    "brief": r.brief,
                    "key_topics": r.key_topics,
                    "emotional_tone": r.emotional_tone,
                    "homework_assigned": r.homework_assigned,
                    "follow_ups": r.follow_ups,
                    "risk_flags": r.risk_flags,
                    "model_name": r.model_name,
                    "generated_at": _iso(r.generated_at),
                }
                for r in recaps
            ],
            "transcripts": [
                {
                    "id": str(t.id),
                    "session_id": str(t.session_id),
                    "full_text": t.full_text,
                    "segments": t.segments,
                    "word_count": t.word_count,
                    "duration_seconds": t.duration_seconds,
                    "language": t.language,
                    "confidence": t.confidence,
                    "metadata": t.transcript_metadata,
                }
                for t in transcripts
            ],
            "themes": (
                {
                    "id": str(themes.id),
                    "recurring_topics": themes.recurring_topics,
                    "emotional_patterns": themes.emotional_patterns,
                    "coping_strategies": themes.coping_strategies,
                    "progress_indicators": themes.progress_indicators,
                    "ongoing_concerns": themes.ongoing_concerns,
                    "source_session_count": themes.source_session_count,
                    "model_name": themes.model_name,
                    "generated_at": _iso(themes.generated_at),
                }
                if themes is not None
                else None
            ),
            "conversations": [
                {
                    "id": str(c.id),
                    "title": c.title,
                    "message_count": c.message_count,
                    "created_at": _iso(c.created_at),
                    "updated_at": _iso(c.updated_at),
                    "messages": [
                        {
                            "id": str(m.id),
                            "role": m.role.value,
                            "content": m.content,
                            "sequence_number": m.sequence_number,
                            "sources": m.sources,
                            "created_at": _iso(m.created_at),
                        }
                        for m in messages
                        if m.conversation_id == c.id
                    ],
                }
                for c in conversations
            ],
            "assessments": [
                {
                    "id": str(a.id),
                    "instrument": a.instrument.value,
                    "responses": a.responses,
                    "total_score": a.total_score,
                    "severity": a.severity,
                    "notes": a.notes,
                    "administered_at": _iso(a.administered_at),
                    "administered_by_user_id": (
                        str(a.administered_by_user_id)
                        if a.administered_by_user_id is not None
                        else None
                    ),
                }
                for a in assessments
            ],
        }

    async def delete_patient(
        self,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Hard-delete a patient and all data cascading from the user row.

        Writes a tombstone ``patient.data_deleted`` analytics event BEFORE
        the delete so the audit record persists after the patient,
        sessions, and transcripts are gone. Cascades handle the rest.
        """
        patient = await self._load_patient_in_org(patient_id, org_id)

        session_count_row = await self.db_session.execute(
            select(SessionRecording.id).where(
                SessionRecording.patient_id == patient_id
            )
        )
        session_count = len(list(session_count_row.scalars().all()))

        transcript_count_row = await self.db_session.execute(
            select(Transcript.id)
            .join(
                SessionRecording,
                SessionRecording.id == Transcript.session_id,
            )
            .where(SessionRecording.patient_id == patient_id)
        )
        transcript_count = len(list(transcript_count_row.scalars().all()))

        conversation_count_row = await self.db_session.execute(
            select(Conversation.id).where(Conversation.patient_id == patient_id)
        )
        conversation_count = len(list(conversation_count_row.scalars().all()))

        tombstone = AnalyticsEvent(
            event_name="patient.data_deleted",
            event_category=EventCategory.SYSTEM,
            organization_id=org_id,
            actor_id=therapist_id,
            properties={
                "patient_id": str(patient_id),
                "triggered_by": str(therapist_id),
                "session_count_deleted": session_count,
                "transcript_count_deleted": transcript_count,
                "conversation_count_deleted": conversation_count,
            },
            event_timestamp=datetime.now(UTC),
            received_at=datetime.now(UTC),
            # HIPAA: the record of the deletion must survive the retention
            # purge even after the underlying patient row is gone.
            retain_forever=True,
        )
        self.db_session.add(tombstone)
        await self.db_session.flush()

        await self.db_session.delete(patient)
        await self.db_session.flush()

        logger.info(
            "Patient %s deleted by therapist %s (org=%s, sessions=%d)",
            patient_id,
            therapist_id,
            org_id,
            session_count,
        )
        return {
            "patient_id": str(patient_id),
            "session_count_deleted": session_count,
            "transcript_count_deleted": transcript_count,
            "conversation_count_deleted": conversation_count,
            "deleted_at": datetime.now(UTC).isoformat(),
        }

    async def _load_patient_in_org(
        self,
        patient_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> User:
        """Fetch the patient row and verify it belongs to the caller's org."""
        result = await self.db_session.execute(
            select(User).where(User.id == patient_id)
        )
        patient = result.scalar_one_or_none()
        if patient is None:
            raise NotFoundError(resource="Patient", resource_id=str(patient_id))
        if patient.role != UserRole.PATIENT:
            raise NotFoundError(resource="Patient", resource_id=str(patient_id))
        if patient.organization_id != org_id:
            raise ForbiddenError("Patient does not belong to your organization")
        return patient
