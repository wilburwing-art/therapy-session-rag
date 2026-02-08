"""Service for session management."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenError, NotFoundError
from src.core.pagination import CursorPage, create_cursor_page
from src.core.tenant import TenantContext
from src.models.db.consent import ConsentType
from src.models.db.session import Session, SessionStatus
from src.models.domain.session import (
    SessionCreate,
    SessionFilter,
    SessionRead,
    SessionSummary,
    SessionUpdate,
)
from src.models.domain.session import SessionStatus as DomainSessionStatus
from src.models.domain.session import (
    SessionType as DomainSessionType,
)
from src.repositories.consent_repo import ConsentRepository
from src.repositories.session_repo import SessionRepository


class SessionService:
    """Service for managing therapy sessions."""

    def __init__(
        self,
        db_session: AsyncSession,
        tenant: TenantContext | None = None,
    ) -> None:
        self.db_session = db_session
        self.session_repo = SessionRepository(db_session)
        self.consent_repo = ConsentRepository(db_session)
        self.tenant = tenant

    async def create_session(self, create: SessionCreate) -> SessionRead:
        """Create a new session.

        Validates that the patient has granted consent for recording
        before creating the session.

        Args:
            create: Session creation data

        Returns:
            The created session

        Raises:
            ForbiddenError: If patient has not granted recording consent
            ForbiddenError: If users don't belong to the authenticated organization
        """
        # Validate tenant access - ensure patient and therapist belong to org
        if self.tenant:
            await self.tenant.validate_users_in_org(
                create.patient_id, create.therapist_id
            )

        # Check for active recording consent
        consent = await self.consent_repo.get_active_consent(
            patient_id=create.patient_id,
            therapist_id=create.therapist_id,
            consent_type=ConsentType.RECORDING,
        )

        if not consent:
            raise ForbiddenError(
                detail="Patient has not granted consent for recording. "
                "Obtain consent before creating a session."
            )

        # Create session
        session = Session(
            patient_id=create.patient_id,
            therapist_id=create.therapist_id,
            consent_id=create.consent_id,
            session_date=create.session_date,
            status=SessionStatus.PENDING,
            session_metadata=create.session_metadata,
        )

        created = await self.session_repo.create(session)
        return self._to_session_read(created)

    async def get_session(self, session_id: uuid.UUID) -> SessionRead:
        """Get a session by ID.

        Args:
            session_id: The session ID

        Returns:
            The session

        Raises:
            NotFoundError: If session not found
            ForbiddenError: If session belongs to a different organization
        """
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        # Validate tenant access
        if self.tenant:
            await self.tenant.validate_session_access(session_id)

        return self._to_session_read(session)

    async def update_session(
        self,
        session_id: uuid.UUID,
        update: SessionUpdate,
    ) -> SessionRead:
        """Update a session.

        Args:
            session_id: The session ID
            update: Update data

        Returns:
            The updated session

        Raises:
            NotFoundError: If session not found
            ForbiddenError: If session belongs to a different organization
        """
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise NotFoundError(resource="Session", resource_id=str(session_id))

        # Validate tenant access
        if self.tenant:
            await self.tenant.validate_session_access(session_id)

        # Update status if provided
        if update.status is not None:
            db_status = SessionStatus(update.status.value)
            await self.session_repo.update_status(
                session_id=session_id,
                status=db_status,
                error_message=update.error_message,
            )

        # Update recording info if provided
        if update.recording_path is not None:
            await self.session_repo.update_recording_info(
                session_id=session_id,
                recording_path=update.recording_path,
                recording_duration_seconds=update.recording_duration_seconds,
            )

        # Refresh and return
        await self.db_session.refresh(session)
        return self._to_session_read(session)

    async def update_status(
        self,
        session_id: uuid.UUID,
        status: DomainSessionStatus,
        error_message: str | None = None,
    ) -> bool:
        """Update session status.

        Args:
            session_id: The session ID
            status: New status
            error_message: Optional error message (for FAILED status)

        Returns:
            True if session was updated, False if not found
        """
        db_status = SessionStatus(status.value)
        return await self.session_repo.update_status(
            session_id=session_id,
            status=db_status,
            error_message=error_message,
        )

    async def list_sessions(
        self,
        filter_params: SessionFilter | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SessionSummary]:
        """List sessions with optional filters.

        Args:
            filter_params: Optional filter parameters
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of session summaries
        """
        db_status = None
        if filter_params and filter_params.status:
            db_status = SessionStatus(filter_params.status.value)

        sessions = await self.session_repo.list_sessions(
            patient_id=filter_params.patient_id if filter_params else None,
            therapist_id=filter_params.therapist_id if filter_params else None,
            status=db_status,
            date_from=filter_params.date_from if filter_params else None,
            date_to=filter_params.date_to if filter_params else None,
            limit=limit,
            offset=offset,
        )

        return [self._to_session_summary(s) for s in sessions]

    async def get_sessions_for_patient(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID | None = None,
        status: DomainSessionStatus | None = None,
    ) -> list[SessionSummary]:
        """Get all sessions for a patient.

        Args:
            patient_id: The patient ID
            therapist_id: Optional filter by therapist
            status: Optional filter by status

        Returns:
            List of session summaries
        """
        db_status = SessionStatus(status.value) if status else None

        sessions = await self.session_repo.list_sessions(
            patient_id=patient_id,
            therapist_id=therapist_id,
            status=db_status,
        )

        return [self._to_session_summary(s) for s in sessions]

    async def list_sessions_paginated(
        self,
        filter_params: SessionFilter | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> CursorPage[SessionSummary]:
        """List sessions with cursor-based pagination.

        Args:
            filter_params: Optional filter parameters
            cursor: Pagination cursor from previous response
            limit: Maximum number of results per page

        Returns:
            CursorPage with session summaries
        """
        db_status = None
        if filter_params and filter_params.status:
            db_status = SessionStatus(filter_params.status.value)

        sessions = await self.session_repo.list_sessions_cursor(
            patient_id=filter_params.patient_id if filter_params else None,
            therapist_id=filter_params.therapist_id if filter_params else None,
            status=db_status,
            cursor=cursor,
            limit=limit,
        )

        summaries = [self._to_session_summary(s) for s in sessions]

        return create_cursor_page(
            items=summaries,
            limit=limit,
            get_sort_value=lambda s: s.session_date,
            get_id=lambda s: s.id,
        )

    def _to_session_read(self, session: Session) -> SessionRead:
        """Convert Session DB model to SessionRead schema."""
        return SessionRead(
            id=session.id,
            patient_id=session.patient_id,
            therapist_id=session.therapist_id,
            consent_id=session.consent_id,
            session_date=session.session_date,
            recording_path=session.recording_path,
            recording_duration_seconds=session.recording_duration_seconds,
            status=DomainSessionStatus(session.status.value),
            session_type=DomainSessionType(session.session_type.value),
            error_message=session.error_message,
            session_metadata=session.session_metadata,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _to_session_summary(self, session: Session) -> SessionSummary:
        """Convert Session DB model to SessionSummary schema."""
        return SessionSummary(
            id=session.id,
            patient_id=session.patient_id,
            therapist_id=session.therapist_id,
            session_date=session.session_date,
            status=DomainSessionStatus(session.status.value),
            session_type=DomainSessionType(session.session_type.value),
            recording_duration_seconds=session.recording_duration_seconds,
            created_at=session.created_at,
        )
