"""Full-text search service.

Thin validation + delegation layer over :class:`SearchRepository`. Centralizes
query-string validation so the endpoint handler and any future callers get
the same bounds.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError
from src.models.domain.search import SearchHit
from src.repositories.search_repo import SearchRepository

# Bounds on the free-text query. 2 chars guards against trigger-happy single
# keystrokes (which would return half the dataset), 200 chars is plenty for a
# "what did we talk about" natural-language query and keeps the tsquery cost
# bounded.
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 200

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class SearchService:
    """Validates search input and calls the repository."""

    def __init__(self, db_session: AsyncSession) -> None:
        self._repo = SearchRepository(db_session)

    async def search_sessions(
        self,
        organization_id: uuid.UUID,
        query: str,
        patient_id: uuid.UUID | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[SearchHit]:
        """Validate ``query`` and return matching session hits."""
        cleaned = self._validate_query(query)
        bounded_limit = self._validate_limit(limit)
        return await self._repo.search_across(
            organization_id=organization_id,
            query=cleaned,
            patient_id=patient_id,
            limit=bounded_limit,
        )

    @staticmethod
    def _validate_query(query: str) -> str:
        """Trim and length-check the user query."""
        if query is None:
            raise ValidationError(detail="Search query is required.")
        cleaned = query.strip()
        if not cleaned:
            raise ValidationError(detail="Search query must not be empty.")
        if len(cleaned) < MIN_QUERY_LENGTH:
            raise ValidationError(
                detail=(
                    f"Search query must be at least {MIN_QUERY_LENGTH} characters."
                )
            )
        if len(cleaned) > MAX_QUERY_LENGTH:
            raise ValidationError(
                detail=(
                    f"Search query must be at most {MAX_QUERY_LENGTH} characters."
                )
            )
        return cleaned

    @staticmethod
    def _validate_limit(limit: int) -> int:
        """Clamp the limit to a safe range."""
        if limit < 1:
            return 1
        if limit > MAX_LIMIT:
            return MAX_LIMIT
        return limit
