"""Full-text search repository.

Executes three parameterized Postgres FTS queries — one against transcripts,
one against session_recaps, one against sessions.therapist_notes — unions the
results, and returns the top N by ``ts_rank_cd`` rank.

All queries are organization-scoped via joins to sessions → users, and all
string inputs are passed as bound parameters so the search query text is
never string-interpolated into SQL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.domain.search import SearchHit, SearchSource

# ts_headline options: keep snippets short for card rendering and use <mark>
# so the frontend can apply a single highlight style. HighlightAll=false so
# we get "around the match" rather than the entire document.
_HEADLINE_OPTIONS = "MaxWords=30, MinWords=5, HighlightAll=false, StartSel=<mark>, StopSel=</mark>"

# Transcript search: join transcripts → sessions → patient user for org scope.
_TRANSCRIPT_SQL = f"""
SELECT
    s.id AS session_id,
    s.patient_id AS patient_id,
    u.full_name AS patient_name,
    s.session_date AS session_date,
    ts_rank_cd(t.search_vector, q.query) AS rank,
    ts_headline(
        'english',
        t.full_text,
        q.query,
        '{_HEADLINE_OPTIONS}'
    ) AS snippet
FROM transcripts AS t
JOIN sessions AS s ON s.id = t.session_id
JOIN users AS u ON u.id = s.patient_id
CROSS JOIN LATERAL (SELECT plainto_tsquery('english', :q) AS query) AS q
WHERE u.organization_id = :organization_id
    AND t.search_vector @@ q.query
    AND (:patient_id IS NULL OR s.patient_id = :patient_id)
"""

# Recap search: search_vector built from brief + key_topics. For the snippet
# we concatenate brief and key_topics::text into a plain text so
# ts_headline has something to highlight.
_RECAP_SQL = f"""
SELECT
    s.id AS session_id,
    s.patient_id AS patient_id,
    u.full_name AS patient_name,
    s.session_date AS session_date,
    ts_rank_cd(r.search_vector, q.query) AS rank,
    ts_headline(
        'english',
        coalesce(r.brief, '') || ' ' || coalesce(r.key_topics::text, ''),
        q.query,
        '{_HEADLINE_OPTIONS}'
    ) AS snippet
FROM session_recaps AS r
JOIN sessions AS s ON s.id = r.session_id
JOIN users AS u ON u.id = s.patient_id
CROSS JOIN LATERAL (SELECT plainto_tsquery('english', :q) AS query) AS q
WHERE u.organization_id = :organization_id
    AND r.search_vector @@ q.query
    AND (:patient_id IS NULL OR s.patient_id = :patient_id)
"""

# Therapist-notes search: search_vector lives directly on sessions.
_NOTES_SQL = f"""
SELECT
    s.id AS session_id,
    s.patient_id AS patient_id,
    u.full_name AS patient_name,
    s.session_date AS session_date,
    ts_rank_cd(s.search_vector, q.query) AS rank,
    ts_headline(
        'english',
        coalesce(s.therapist_notes, ''),
        q.query,
        '{_HEADLINE_OPTIONS}'
    ) AS snippet
FROM sessions AS s
JOIN users AS u ON u.id = s.patient_id
CROSS JOIN LATERAL (SELECT plainto_tsquery('english', :q) AS query) AS q
WHERE u.organization_id = :organization_id
    AND s.therapist_notes IS NOT NULL
    AND s.search_vector @@ q.query
    AND (:patient_id IS NULL OR s.patient_id = :patient_id)
"""


@dataclass(frozen=True)
class _SearchQuery:
    """Internal bundle of a SQL template and the source label for its rows."""

    sql: str
    source: SearchSource


_SEARCH_QUERIES: tuple[_SearchQuery, ...] = (
    _SearchQuery(sql=_TRANSCRIPT_SQL, source=SearchSource.TRANSCRIPT),
    _SearchQuery(sql=_RECAP_SQL, source=SearchSource.RECAP),
    _SearchQuery(sql=_NOTES_SQL, source=SearchSource.NOTES),
)


class SearchRepository:
    """Data-access layer for cross-session full-text search."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def search_across(
        self,
        organization_id: uuid.UUID,
        query: str,
        patient_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        """Search transcripts, recaps, and therapist notes for ``query``.

        Results from all three sources are merged, sorted by ``ts_rank_cd``
        descending, and truncated to ``limit``. All values flow through
        bound parameters; the query text is never string-interpolated into
        SQL. Organization scope is enforced via a join to the patient's
        ``users`` row.
        """
        params = {
            "q": query,
            "organization_id": organization_id,
            "patient_id": patient_id,
        }

        hits: list[SearchHit] = []
        for search_query in _SEARCH_QUERIES:
            result = await self.db_session.execute(
                text(search_query.sql),
                params,
            )
            rows: list[Row[tuple[uuid.UUID, uuid.UUID, str | None, datetime, float, str]]] = list(
                result.all()
            )
            for row in rows:
                hits.append(
                    SearchHit(
                        session_id=row.session_id,
                        patient_id=row.patient_id,
                        patient_name=row.patient_name,
                        session_date=row.session_date,
                        source=search_query.source,
                        snippet=row.snippet,
                        rank=float(row.rank),
                    )
                )

        hits.sort(key=lambda h: h.rank, reverse=True)
        return hits[:limit]
