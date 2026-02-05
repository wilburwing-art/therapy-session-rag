"""Load stage - creates DB scaffolding and loads processed data."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.consent import Consent, ConsentStatus, ConsentType
from src.models.db.organization import Organization
from src.models.db.session import Session, SessionStatus
from src.models.db.session_chunk import SessionChunk
from src.models.db.transcript import Transcript
from src.models.db.user import User, UserRole

DEV_ORG_NAME = "Dev Pipeline"
DEV_PATIENT_EMAIL = "dev-patient@therapyrag.local"
DEV_THERAPIST_EMAIL = "dev-therapist@therapyrag.local"


async def get_or_create_dev_org(db: AsyncSession) -> Organization:
    """Get or create the dev organization."""
    result = await db.execute(
        select(Organization).where(Organization.name == DEV_ORG_NAME)
    )
    org = result.scalar_one_or_none()
    if org:
        return org

    org = Organization(name=DEV_ORG_NAME)
    db.add(org)
    await db.flush()
    return org


async def get_or_create_dev_user(
    db: AsyncSession, org_id: uuid.UUID, email: str, role: UserRole
) -> User:
    """Get or create a dev user."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        return user

    user = User(
        organization_id=org_id,
        email=email,
        role=role,
        full_name=f"Dev {role.value.title()}",
        hashed_password="not-a-real-hash",
    )
    db.add(user)
    await db.flush()
    return user


async def get_or_create_dev_consent(
    db: AsyncSession,
    patient_id: uuid.UUID,
    therapist_id: uuid.UUID,
) -> Consent:
    """Get or create dev consent records."""
    result = await db.execute(
        select(Consent).where(
            Consent.patient_id == patient_id,
            Consent.therapist_id == therapist_id,
            Consent.status == ConsentStatus.GRANTED,
            Consent.consent_type == ConsentType.RECORDING,
        )
    )
    consent = result.scalar_one_or_none()
    if consent:
        return consent

    consent = Consent(
        patient_id=patient_id,
        therapist_id=therapist_id,
        consent_type=ConsentType.RECORDING,
        status=ConsentStatus.GRANTED,
        granted_at=datetime.now(UTC),
        ip_address="127.0.0.1",
        user_agent="dev-pipeline",
    )
    db.add(consent)
    await db.flush()
    return consent


async def setup_dev_scaffolding(
    db: AsyncSession,
) -> tuple[Organization, User, User, Consent]:
    """Create all dev scaffolding (org, users, consent). Idempotent."""
    org = await get_or_create_dev_org(db)
    patient = await get_or_create_dev_user(db, org.id, DEV_PATIENT_EMAIL, UserRole.PATIENT)
    therapist = await get_or_create_dev_user(
        db, org.id, DEV_THERAPIST_EMAIL, UserRole.THERAPIST
    )
    consent = await get_or_create_dev_consent(db, patient.id, therapist.id)
    await db.commit()
    return org, patient, therapist, consent


async def find_session_by_content_hash(
    db: AsyncSession, content_hash: str
) -> Session | None:
    """Find an existing session by content hash in metadata."""
    result = await db.execute(
        select(Session).where(
            Session.session_metadata["content_hash"].as_string() == content_hash
        )
    )
    return result.scalar_one_or_none()


async def delete_session_data(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Delete transcript and chunks for a session (for re-loading)."""
    # Delete chunks first (FK to transcript)
    chunks_result = await db.execute(
        select(SessionChunk).where(SessionChunk.session_id == session_id)
    )
    for chunk in chunks_result.scalars().all():
        await db.delete(chunk)

    # Delete transcript
    transcript_result = await db.execute(
        select(Transcript).where(Transcript.session_id == session_id)
    )
    transcript = transcript_result.scalar_one_or_none()
    if transcript:
        await db.delete(transcript)

    await db.flush()


async def load_to_database(
    db: AsyncSession,
    audio_path: str,
    content_hash: str,
    transcript_data: dict[str, Any],
    chunks: list[dict[str, Any]],
    embeddings: list[dict[str, Any]],
    patient: User,
    therapist: User,
    consent: Consent,
) -> uuid.UUID:
    """Load processed pipeline data into the database.

    Idempotent: if a session with this content hash exists,
    its transcript and chunks are replaced.
    """
    existing = await find_session_by_content_hash(db, content_hash)

    if existing:
        session_id = existing.id
        await delete_session_data(db, session_id)
        existing.status = SessionStatus.READY
        await db.flush()
    else:
        session = Session(
            patient_id=patient.id,
            therapist_id=therapist.id,
            consent_id=consent.id,
            session_date=datetime.now(UTC),
            status=SessionStatus.READY,
            session_metadata={
                "content_hash": content_hash,
                "source_file": str(audio_path),
            },
        )
        db.add(session)
        await db.flush()
        session_id = session.id

    # Create transcript
    transcript = Transcript(
        session_id=session_id,
        full_text=transcript_data["full_text"],
        segments=transcript_data.get("segments", []),
        word_count=transcript_data.get("word_count"),
        duration_seconds=transcript_data.get("duration_seconds"),
        language=transcript_data.get("language"),
        confidence=transcript_data.get("confidence"),
    )
    db.add(transcript)
    await db.flush()

    # Create chunks with embeddings
    for i, (chunk_data, embed_data) in enumerate(zip(chunks, embeddings)):
        chunk = SessionChunk(
            session_id=session_id,
            transcript_id=transcript.id,
            chunk_index=i,
            content=chunk_data["content"],
            embedding=embed_data["embedding"],
            start_time=chunk_data.get("start_time"),
            end_time=chunk_data.get("end_time"),
            speaker=chunk_data.get("speaker"),
            token_count=embed_data.get("token_count"),
            chunk_metadata={"segment_indices": chunk_data.get("segment_indices", [])},
        )
        db.add(chunk)

    await db.commit()
    return session_id
