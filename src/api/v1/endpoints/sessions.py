"""Session API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse

from src.api.v1.dependencies import Auth
from src.core.config import get_settings
from src.core.database import DbSession
from src.core.exceptions import ValidationError
from src.core.pagination import CursorPage
from src.core.tenant import TenantContext
from src.models.domain.session import (
    SessionCreate,
    SessionFilter,
    SessionRead,
    SessionSummary,
    SessionUpdate,
    SessionUploadResponse,
)
from src.models.domain.session import SessionStatus as DomainSessionStatus
from src.models.domain.transcript import (
    TranscriptionJobRead,
    TranscriptionStatusResponse,
    TranscriptRead,
)
from src.services.session_service import SessionService
from src.services.storage_service import StorageService
from src.services.transcription_service import TranscriptionService
from src.workers.transcription_worker import queue_transcription

router = APIRouter()

# Allowed audio MIME types
ALLOWED_AUDIO_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/webm",
    "audio/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
}

# Maximum file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024


def get_session_service(session: DbSession, auth: Auth) -> SessionService:
    """Get session service instance with tenant context."""
    tenant = TenantContext(
        organization_id=auth.organization_id,
        db_session=session,
    )
    return SessionService(session, tenant=tenant)


def get_storage_service() -> StorageService:
    """Get storage service instance."""
    return StorageService(settings=get_settings())


def get_transcription_service(session: DbSession) -> TranscriptionService:
    """Get transcription service instance."""
    return TranscriptionService(session)


SessionSvc = Annotated[SessionService, Depends(get_session_service)]
StorageSvc = Annotated[StorageService, Depends(get_storage_service)]
TranscriptSvc = Annotated[TranscriptionService, Depends(get_transcription_service)]


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(
    create: SessionCreate,
    service: SessionSvc,
) -> SessionRead:
    """Create a new therapy session.

    Validates that the patient has granted recording consent before
    creating the session. Returns 403 Forbidden if consent is not granted.
    """
    return await service.create_session(create)


@router.get("/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: uuid.UUID,
    service: SessionSvc,
) -> SessionRead:
    """Get a session by ID.

    Returns 404 if session not found.
    """
    return await service.get_session(session_id)


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: uuid.UUID,
    update: SessionUpdate,
    service: SessionSvc,
) -> SessionRead:
    """Update a session.

    Can update status, recording path, error message, etc.
    Returns 404 if session not found.
    """
    return await service.update_session(session_id, update)


@router.get("", response_model=CursorPage[SessionSummary])
async def list_sessions(
    service: SessionSvc,
    patient_id: Annotated[
        uuid.UUID | None, Query(description="Filter by patient ID")
    ] = None,
    therapist_id: Annotated[
        uuid.UUID | None, Query(description="Filter by therapist ID")
    ] = None,
    status: Annotated[
        DomainSessionStatus | None, Query(description="Filter by status")
    ] = None,
    cursor: Annotated[
        str | None, Query(description="Pagination cursor from previous response")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum results")] = 50,
) -> CursorPage[SessionSummary]:
    """List sessions with cursor-based pagination.

    Returns a paginated list of session summaries with a cursor for the next page.
    Use the `next_cursor` value in subsequent requests to get more results.
    """
    filter_params = SessionFilter(
        patient_id=patient_id,
        therapist_id=therapist_id,
        status=status,
    )
    return await service.list_sessions_paginated(
        filter_params=filter_params,
        cursor=cursor,
        limit=limit,
    )


@router.post("/{session_id}/recording", response_model=SessionUploadResponse)
async def upload_recording(
    session_id: uuid.UUID,
    session_service: SessionSvc,
    storage_service: StorageSvc,
    file: Annotated[UploadFile, File(description="Audio file to upload")],
) -> SessionUploadResponse:
    """Upload a recording for a session.

    Accepts audio files (mp3, wav, webm, ogg, flac, m4a).
    Maximum file size is 100MB.

    The session status will be updated to 'uploaded' after successful upload.
    Returns 404 if session not found.
    Returns 400 if file type is not supported or file is too large.
    """
    # Validate session exists
    session = await session_service.get_session(session_id)

    # Validate file type
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise ValidationError(
            detail=f"Unsupported file type: {content_type}. "
            f"Allowed types: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}"
        )

    # Read file content and validate size
    file_content = await file.read()
    file_size = len(file_content)

    if file_size > MAX_FILE_SIZE:
        raise ValidationError(
            detail=f"File too large: {file_size} bytes. Maximum allowed: {MAX_FILE_SIZE} bytes"
        )

    if file_size == 0:
        raise ValidationError(detail="File is empty")

    # Generate storage key
    filename = file.filename or "recording"
    storage_key = storage_service.generate_key(filename, prefix="recordings")

    # Upload to storage
    await storage_service.upload_file(
        file_data=file_content,
        key=storage_key,
        content_type=content_type,
    )

    # Update session with recording path and status
    update = SessionUpdate(
        recording_path=storage_key,
        status=DomainSessionStatus.UPLOADED,
    )
    await session_service.update_session(session_id, update)

    return SessionUploadResponse(
        session_id=session.id,
        recording_path=storage_key,
        file_size=file_size,
        status=DomainSessionStatus.UPLOADED,
    )


@router.get("/patient/{patient_id}", response_model=list[SessionSummary])
async def get_patient_sessions(
    patient_id: uuid.UUID,
    service: SessionSvc,
    therapist_id: Annotated[
        uuid.UUID | None, Query(description="Filter by therapist ID")
    ] = None,
    status: Annotated[
        DomainSessionStatus | None, Query(description="Filter by status")
    ] = None,
) -> list[SessionSummary]:
    """Get all sessions for a patient.

    Returns sessions for the specified patient, optionally filtered
    by therapist and/or status.
    """
    return await service.get_sessions_for_patient(
        patient_id=patient_id,
        therapist_id=therapist_id,
        status=status,
    )


@router.post("/{session_id}/transcribe", response_model=TranscriptionJobRead, status_code=202)
async def start_transcription(
    session_id: uuid.UUID,
    session_service: SessionSvc,
    transcription_service: TranscriptSvc,
) -> TranscriptionJobRead:
    """Start transcription for a session.

    Creates a transcription job and queues it for processing.
    The session must have a recording uploaded first.

    Returns 202 Accepted with the job details.
    Returns 404 if session not found.
    Returns 400 if session has no recording.
    """
    # Verify session exists and has a recording
    session = await session_service.get_session(session_id)
    if not session.recording_path:
        raise ValidationError(
            detail="Session has no recording. Upload a recording first."
        )

    # Create transcription job
    job = await transcription_service.create_transcription_job(session_id)

    # Queue for background processing
    queue_transcription(job.id)

    return job


@router.get("/{session_id}/transcript", response_model=TranscriptRead)
async def get_transcript(
    session_id: uuid.UUID,
    session_service: SessionSvc,
    transcription_service: TranscriptSvc,
) -> TranscriptRead:
    """Get the transcript for a session.

    Returns the full transcript including segments with speaker diarization.
    Returns 404 if session or transcript not found.
    """
    # Validate session access via tenant context
    await session_service.get_session(session_id)
    return await transcription_service.get_transcript(session_id)


@router.get(
    "/{session_id}/transcription-status",
    response_model=TranscriptionStatusResponse,
    responses={
        200: {"description": "Transcription completed or failed"},
        202: {"description": "Transcription still in progress"},
    },
)
async def get_transcription_status(
    session_id: uuid.UUID,
    session_service: SessionSvc,
    transcription_service: TranscriptSvc,
) -> JSONResponse:
    """Get the transcription status for a session.

    Returns 200 if transcription is completed or failed.
    Returns 202 if transcription is still in progress (pending or processing).
    """
    # Validate session access via tenant context
    await session_service.get_session(session_id)
    status = await transcription_service.get_transcription_status(session_id)

    # Determine HTTP status code based on job status
    if status.job_status in ("pending", "processing"):
        return JSONResponse(
            status_code=202,
            content=status.model_dump(mode="json"),
        )

    return JSONResponse(
        status_code=200,
        content=status.model_dump(mode="json"),
    )
