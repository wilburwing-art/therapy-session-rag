"""Full-text search API endpoint.

Therapists hit ``GET /api/v1/search?q=...`` to find past sessions by transcript
content, recap summary, key topics, or private therapist notes. Auth is via
the shared ``Auth`` dependency, which accepts either a therapist JWT cookie
(for the web app) or an ``X-API-Key`` header (for server-to-server traffic).
The endpoint is gated behind an entitled subscription by the router.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.v1.dependencies import Auth
from src.core.database import DbSession
from src.models.domain.search import SearchHit
from src.services.search_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_QUERY_LENGTH,
    MIN_QUERY_LENGTH,
    SearchService,
)

router = APIRouter()


def get_search_service(session: DbSession) -> SearchService:
    """Get search service instance."""
    return SearchService(session)


SearchSvc = Annotated[SearchService, Depends(get_search_service)]


@router.get("", response_model=list[SearchHit])
async def search_sessions(
    auth: Auth,
    service: SearchSvc,
    q: Annotated[
        str,
        Query(
            min_length=MIN_QUERY_LENGTH,
            max_length=MAX_QUERY_LENGTH,
            description="Full-text search query (2-200 chars)",
        ),
    ],
    patient_id: Annotated[
        uuid.UUID | None,
        Query(description="Optional: restrict results to a single patient"),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_LIMIT,
            description=f"Maximum results to return (1-{MAX_LIMIT})",
        ),
    ] = DEFAULT_LIMIT,
) -> list[SearchHit]:
    """Search across transcripts, recaps, and therapist notes.

    Returns the top ``limit`` matches ranked by ``ts_rank_cd`` descending.
    Snippets contain ``<mark>`` tags around matched terms; the frontend
    is expected to sanitize/render them.
    """
    return await service.search_sessions(
        organization_id=auth.organization_id,
        query=q,
        patient_id=patient_id,
        limit=limit,
    )
