"""Repository for transcript operations."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.transcript import (
    Transcript,
    TranscriptionJob,
    TranscriptionJobStatus,
)


class TranscriptRepository:
    """Repository for transcript database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, job: TranscriptionJob) -> TranscriptionJob:
        """Create a new transcription job.

        Args:
            job: The transcription job to create

        Returns:
            The created job
        """
        self.session.add(job)
        await self.session.flush()
        await self.session.refresh(job)
        return job

    async def get_job_by_id(self, job_id: uuid.UUID) -> TranscriptionJob | None:
        """Get a transcription job by ID.

        Args:
            job_id: The job ID

        Returns:
            The job if found, None otherwise
        """
        result = await self.session.execute(
            select(TranscriptionJob).where(TranscriptionJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_job_for_session(
        self, session_id: uuid.UUID
    ) -> TranscriptionJob | None:
        """Get the most recent transcription job for a session.

        Args:
            session_id: The session ID

        Returns:
            The most recent job if found, None otherwise
        """
        result = await self.session.execute(
            select(TranscriptionJob)
            .where(TranscriptionJob.session_id == session_id)
            .order_by(TranscriptionJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_job_status(
        self,
        job_id: uuid.UUID,
        status: TranscriptionJobStatus,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> bool:
        """Update transcription job status.

        Args:
            job_id: The job ID
            status: New status
            error_message: Optional error message
            started_at: When processing started
            completed_at: When processing completed

        Returns:
            True if updated, False if not found
        """
        values: dict[str, TranscriptionJobStatus | str | datetime | None] = {
            "status": status
        }
        if error_message is not None:
            values["error_message"] = error_message
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at

        cursor_result = await self.session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(**values)
        )
        rowcount = getattr(cursor_result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    async def increment_retry_count(self, job_id: uuid.UUID) -> bool:
        """Increment the retry count for a job.

        Args:
            job_id: The job ID

        Returns:
            True if updated, False if not found
        """
        job = await self.get_job_by_id(job_id)
        if not job:
            return False

        cursor_result = await self.session.execute(
            update(TranscriptionJob)
            .where(TranscriptionJob.id == job_id)
            .values(retry_count=job.retry_count + 1)
        )
        rowcount = getattr(cursor_result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    async def create_transcript(self, transcript: Transcript) -> Transcript:
        """Create a new transcript.

        Args:
            transcript: The transcript to create

        Returns:
            The created transcript
        """
        self.session.add(transcript)
        await self.session.flush()
        await self.session.refresh(transcript)
        return transcript

    async def get_transcript_by_id(
        self, transcript_id: uuid.UUID
    ) -> Transcript | None:
        """Get a transcript by ID.

        Args:
            transcript_id: The transcript ID

        Returns:
            The transcript if found, None otherwise
        """
        result = await self.session.execute(
            select(Transcript).where(Transcript.id == transcript_id)
        )
        return result.scalar_one_or_none()

    async def get_transcript_by_session_id(
        self, session_id: uuid.UUID
    ) -> Transcript | None:
        """Get the transcript for a session.

        Args:
            session_id: The session ID

        Returns:
            The transcript if found, None otherwise
        """
        result = await self.session.execute(
            select(Transcript).where(Transcript.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def transcript_exists(self, session_id: uuid.UUID) -> bool:
        """Check if a transcript exists for a session.

        Args:
            session_id: The session ID

        Returns:
            True if transcript exists, False otherwise
        """
        transcript = await self.get_transcript_by_session_id(session_id)
        return transcript is not None
