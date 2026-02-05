"""Service for transcription workflow orchestration."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import NotFoundError
from src.models.db.session import SessionStatus
from src.models.db.transcript import (
    Transcript,
    TranscriptionJob,
    TranscriptionJobStatus,
)
from src.models.domain.transcript import (
    TranscriptionJobRead,
    TranscriptionStatusResponse,
    TranscriptRead,
)
from src.models.domain.transcript import (
    TranscriptionJobStatus as DomainJobStatus,
)
from src.repositories.session_repo import SessionRepository
from src.repositories.transcript_repo import TranscriptRepository
from src.services.deepgram_client import DeepgramClient, DeepgramError
from src.services.storage_service import StorageError, StorageService

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Error during transcription processing."""

    pass


class TranscriptionService:
    """Service for orchestrating transcription workflow.

    Handles the full flow of:
    1. Creating transcription jobs
    2. Downloading audio from storage
    3. Sending to Deepgram for transcription
    4. Storing results
    5. Updating session status
    """

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.session_repo = SessionRepository(db_session)
        self.transcript_repo = TranscriptRepository(db_session)
        self._storage_service: StorageService | None = None
        self._deepgram_client: DeepgramClient | None = None

    @property
    def storage_service(self) -> StorageService:
        """Get or create storage service (lazy initialization)."""
        if self._storage_service is None:
            self._storage_service = StorageService(settings=self.settings)
        return self._storage_service

    @property
    def deepgram_client(self) -> DeepgramClient:
        """Get or create Deepgram client (lazy initialization)."""
        if self._deepgram_client is None:
            self._deepgram_client = DeepgramClient(settings=self.settings)
        return self._deepgram_client

    async def create_transcription_job(
        self, session_id: uuid.UUID
    ) -> TranscriptionJobRead:
        """Create a new transcription job for a session.

        Args:
            session_id: The session to transcribe

        Returns:
            The created transcription job

        Raises:
            NotFoundError: If session not found
        """
        # Verify session exists
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        # Create job
        job = TranscriptionJob(
            session_id=session_id,
            status=TranscriptionJobStatus.PENDING,
        )
        created_job = await self.transcript_repo.create_job(job)

        return self._to_job_read(created_job)

    async def process_transcription(
        self,
        job_id: uuid.UUID,
    ) -> TranscriptRead:
        """Process a transcription job.

        Downloads audio from storage, sends to Deepgram, and stores result.

        Args:
            job_id: The transcription job ID

        Returns:
            The created transcript

        Raises:
            NotFoundError: If job or session not found
            TranscriptionError: If processing fails
        """
        # Get job
        job = await self.transcript_repo.get_job_by_id(job_id)
        if not job:
            raise NotFoundError(resource="TranscriptionJob", resource_id=str(job_id))

        session_id = job.session_id

        # Get session
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        if not session.recording_path:
            await self._fail_job(job_id, session_id, "No recording path set")
            raise TranscriptionError("Session has no recording path")

        try:
            # Update job to processing
            now = datetime.now(UTC)
            await self.transcript_repo.update_job_status(
                job_id=job_id,
                status=TranscriptionJobStatus.PROCESSING,
                started_at=now,
            )

            # Update session status
            await self.session_repo.update_status(
                session_id=session_id,
                status=SessionStatus.TRANSCRIBING,
            )

            # Download audio from storage
            logger.info(f"Downloading audio from {session.recording_path}")
            audio_data = await self._download_audio(session.recording_path)

            # Determine content type from path
            content_type = self._get_content_type(session.recording_path)

            # Transcribe with Deepgram
            logger.info(f"Sending to Deepgram for transcription (job={job_id})")
            result = await self.deepgram_client.transcribe_file(
                audio_data=audio_data,
                content_type=content_type,
                enable_diarization=True,
            )

            # Create transcript record
            transcript = Transcript(
                session_id=session_id,
                job_id=job_id,
                full_text=result.full_text,
                segments=[s.to_dict() for s in result.segments],
                word_count=result.word_count,
                duration_seconds=result.duration_seconds,
                language=result.language,
                confidence=result.confidence,
            )
            created_transcript = await self.transcript_repo.create_transcript(
                transcript
            )

            # Update job to completed
            await self.transcript_repo.update_job_status(
                job_id=job_id,
                status=TranscriptionJobStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )

            # Update session status to embedding
            await self.session_repo.update_status(
                session_id=session_id,
                status=SessionStatus.EMBEDDING,
            )

            logger.info(f"Transcription completed for session {session_id}")

            # Queue embedding job (import here to avoid circular import)
            from src.workers.embedding_worker import queue_embedding
            queue_embedding(session_id)
            logger.info(f"Queued embedding job for session {session_id}")

            return self._to_transcript_read(created_transcript)

        except DeepgramError as e:
            logger.error(f"Deepgram error for job {job_id}: {e}")
            await self._fail_job(job_id, session_id, str(e))
            raise TranscriptionError(f"Transcription failed: {e}") from e

        except StorageError as e:
            logger.error(f"Storage error for job {job_id}: {e}")
            await self._fail_job(job_id, session_id, str(e))
            raise TranscriptionError(f"Failed to download audio: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error for job {job_id}: {e}")
            await self._fail_job(job_id, session_id, str(e))
            raise TranscriptionError(f"Transcription failed: {e}") from e

    async def get_transcription_status(
        self, session_id: uuid.UUID
    ) -> TranscriptionStatusResponse:
        """Get the transcription status for a session.

        Args:
            session_id: The session ID

        Returns:
            Status response with transcript availability and job status
        """
        # Check if transcript exists
        transcript = await self.transcript_repo.get_transcript_by_session_id(
            session_id
        )
        has_transcript = transcript is not None

        # Get latest job status
        job = await self.transcript_repo.get_latest_job_for_session(session_id)
        job_status: DomainJobStatus | None = None
        error_message: str | None = None

        if job:
            job_status = DomainJobStatus(job.status.value)
            error_message = job.error_message

        return TranscriptionStatusResponse(
            session_id=session_id,
            has_transcript=has_transcript,
            job_status=job_status,
            error_message=error_message,
        )

    async def get_transcript(self, session_id: uuid.UUID) -> TranscriptRead:
        """Get the transcript for a session.

        Args:
            session_id: The session ID

        Returns:
            The transcript

        Raises:
            NotFoundError: If transcript not found
        """
        transcript = await self.transcript_repo.get_transcript_by_session_id(
            session_id
        )
        if not transcript:
            raise NotFoundError(
                resource="Transcript",
                detail=f"No transcript found for session {session_id}",
            )

        return self._to_transcript_read(transcript)

    async def retry_transcription(self, job_id: uuid.UUID) -> TranscriptionJobRead:
        """Retry a failed transcription job.

        Args:
            job_id: The job ID to retry

        Returns:
            Updated job

        Raises:
            NotFoundError: If job not found
            TranscriptionError: If job is not in failed state
        """
        job = await self.transcript_repo.get_job_by_id(job_id)
        if not job:
            raise NotFoundError(resource="TranscriptionJob", resource_id=str(job_id))

        if job.status != TranscriptionJobStatus.FAILED:
            raise TranscriptionError(
                f"Can only retry failed jobs. Current status: {job.status.value}"
            )

        # Reset job status and increment retry count
        await self.transcript_repo.update_job_status(
            job_id=job_id,
            status=TranscriptionJobStatus.PENDING,
            error_message=None,
        )
        await self.transcript_repo.increment_retry_count(job_id)

        # Refresh job
        job = await self.transcript_repo.get_job_by_id(job_id)
        return self._to_job_read(job)  # type: ignore[arg-type]

    async def _download_audio(self, recording_path: str) -> bytes:
        """Download audio file from storage.

        Args:
            recording_path: S3 key of the recording

        Returns:
            Audio file bytes
        """
        # Get presigned URL and download
        url = await self.storage_service.get_presigned_url(recording_path)

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    def _get_content_type(self, path: str) -> str:
        """Determine content type from file path.

        Args:
            path: File path

        Returns:
            MIME type string
        """
        extension_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".webm": "audio/webm",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
        }

        for ext, content_type in extension_map.items():
            if path.lower().endswith(ext):
                return content_type

        return "audio/mpeg"  # Default

    async def _fail_job(
        self,
        job_id: uuid.UUID,
        session_id: uuid.UUID,
        error_message: str,
    ) -> None:
        """Mark a job and session as failed.

        Args:
            job_id: The job ID
            session_id: The session ID
            error_message: Error description
        """
        await self.transcript_repo.update_job_status(
            job_id=job_id,
            status=TranscriptionJobStatus.FAILED,
            error_message=error_message,
            completed_at=datetime.now(UTC),
        )

        await self.session_repo.update_status(
            session_id=session_id,
            status=SessionStatus.FAILED,
            error_message=error_message,
        )

    def _to_job_read(self, job: TranscriptionJob) -> TranscriptionJobRead:
        """Convert TranscriptionJob DB model to TranscriptionJobRead schema."""
        return TranscriptionJobRead(
            id=job.id,
            session_id=job.session_id,
            status=DomainJobStatus(job.status.value),
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
            retry_count=job.retry_count,
            created_at=job.created_at,
        )

    def _to_transcript_read(self, transcript: Transcript) -> TranscriptRead:
        """Convert Transcript DB model to TranscriptRead schema."""
        return TranscriptRead(
            id=transcript.id,
            session_id=transcript.session_id,
            job_id=transcript.job_id,
            full_text=transcript.full_text,
            segments=transcript.segments,
            word_count=transcript.word_count,
            duration_seconds=transcript.duration_seconds,
            language=transcript.language,
            confidence=transcript.confidence,
            transcript_metadata=transcript.transcript_metadata,
            created_at=transcript.created_at,
            updated_at=transcript.updated_at,
        )
