"""Repository for session operations."""

import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import decode_cursor
from src.models.db.session import Session, SessionStatus


class SessionRepository:
    """Repository for session database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, session_model: Session) -> Session:
        """Create a new session record.

        Args:
            session_model: The session record to create

        Returns:
            The created session record
        """
        self.session.add(session_model)
        await self.session.flush()
        await self.session.refresh(session_model)
        return session_model

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        """Get a session by ID.

        Args:
            session_id: The session ID

        Returns:
            The session if found, None otherwise
        """
        result = await self.session.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session_id: uuid.UUID,
        status: SessionStatus,
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
        values: dict[str, SessionStatus | str] = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message

        cursor_result = await self.session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(**values)
        )
        rowcount = getattr(cursor_result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    async def update_recording_info(
        self,
        session_id: uuid.UUID,
        recording_path: str,
        recording_duration_seconds: int | None = None,
    ) -> bool:
        """Update session recording information.

        Args:
            session_id: The session ID
            recording_path: S3 key of the recording
            recording_duration_seconds: Duration in seconds

        Returns:
            True if session was updated, False if not found
        """
        values: dict[str, str | int] = {"recording_path": recording_path}
        if recording_duration_seconds is not None:
            values["recording_duration_seconds"] = recording_duration_seconds

        cursor_result = await self.session.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(**values)
        )
        rowcount = getattr(cursor_result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)

    async def list_sessions(
        self,
        patient_id: uuid.UUID | None = None,
        therapist_id: uuid.UUID | None = None,
        status: SessionStatus | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions with optional filters.

        Args:
            patient_id: Filter by patient ID
            therapist_id: Filter by therapist ID
            status: Filter by status
            date_from: Filter sessions after this date
            date_to: Filter sessions before this date
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of sessions matching the filters
        """
        conditions = []

        if patient_id is not None:
            conditions.append(Session.patient_id == patient_id)
        if therapist_id is not None:
            conditions.append(Session.therapist_id == therapist_id)
        if status is not None:
            conditions.append(Session.status == status)
        if date_from is not None:
            conditions.append(Session.session_date >= date_from)
        if date_to is not None:
            conditions.append(Session.session_date <= date_to)

        query = select(Session)
        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Session.session_date.desc()).limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_sessions(
        self,
        patient_id: uuid.UUID | None = None,
        therapist_id: uuid.UUID | None = None,
        status: SessionStatus | None = None,
    ) -> int:
        """Count sessions with optional filters.

        Args:
            patient_id: Filter by patient ID
            therapist_id: Filter by therapist ID
            status: Filter by status

        Returns:
            Number of sessions matching the filters
        """
        from sqlalchemy import func

        conditions = []

        if patient_id is not None:
            conditions.append(Session.patient_id == patient_id)
        if therapist_id is not None:
            conditions.append(Session.therapist_id == therapist_id)
        if status is not None:
            conditions.append(Session.status == status)

        query = select(func.count(Session.id))
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def list_sessions_cursor(
        self,
        patient_id: uuid.UUID | None = None,
        therapist_id: uuid.UUID | None = None,
        status: SessionStatus | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[Session]:
        """List sessions with cursor-based pagination.

        Uses session_date as the sort key with id as tie-breaker.
        Returns limit + 1 items so caller can determine if more exist.

        Args:
            patient_id: Filter by patient ID
            therapist_id: Filter by therapist ID
            status: Filter by status
            cursor: Pagination cursor from previous response
            limit: Maximum number of results (will fetch limit + 1)

        Returns:
            List of sessions matching the filters
        """
        conditions = []

        if patient_id is not None:
            conditions.append(Session.patient_id == patient_id)
        if therapist_id is not None:
            conditions.append(Session.therapist_id == therapist_id)
        if status is not None:
            conditions.append(Session.status == status)

        # Apply cursor condition if provided
        if cursor:
            cursor_data = decode_cursor(cursor)
            cursor_date = datetime.fromisoformat(cursor_data.sort_value)
            cursor_id = uuid.UUID(cursor_data.id)

            # For descending order: get items where (date < cursor_date)
            # OR (date == cursor_date AND id < cursor_id)
            cursor_condition = or_(
                Session.session_date < cursor_date,
                and_(
                    Session.session_date == cursor_date,
                    Session.id < cursor_id,
                ),
            )
            conditions.append(cursor_condition)

        query = select(Session)
        if conditions:
            query = query.where(and_(*conditions))

        # Order by session_date desc, then id desc for consistency
        query = (
            query.order_by(Session.session_date.desc(), Session.id.desc())
            .limit(limit + 1)  # Fetch one extra to detect has_more
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())
