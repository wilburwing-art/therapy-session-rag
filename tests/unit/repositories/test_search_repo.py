"""Unit tests for SearchRepository.

These tests mock ``AsyncSession.execute`` and verify the SQL we hand to
SQLAlchemy:

- Uses parameterized binds (``plainto_tsquery('english', :q)``), never
  string-interpolates the user query.
- Issues three separate statements — one per source table.
- Applies org scope and optional patient filter.
- Produces ``SearchHit`` objects with the right ``source`` label, and
  merges / sorts results by rank.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.domain.search import SearchSource
from src.repositories.search_repo import SearchRepository


def _make_row(
    *,
    session_id: uuid.UUID,
    patient_id: uuid.UUID,
    patient_name: str | None,
    session_date: datetime,
    rank: float,
    snippet: str,
) -> MagicMock:
    row = MagicMock()
    row.session_id = session_id
    row.patient_id = patient_id
    row.patient_name = patient_name
    row.session_date = session_date
    row.rank = rank
    row.snippet = snippet
    return row


def _result_with(rows: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> SearchRepository:
    return SearchRepository(mock_session)


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


class TestSQLStructure:
    """Verify the three SQL statements have the expected shape."""

    async def test_issues_three_statements(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))

        await repo.search_across(org_id, "hello")

        # One statement per source table.
        assert mock_session.execute.await_count == 3

    async def test_uses_parameterized_query_binding(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))

        await repo.search_across(org_id, "sleep anxiety")

        for call in mock_session.execute.await_args_list:
            args, _ = call
            sql = str(args[0])
            params = args[1]

            # Never interpolate the query text into SQL.
            assert "sleep anxiety" not in sql
            # Always use plainto_tsquery with bound :q.
            assert "plainto_tsquery('english', :q)" in sql
            # Bound parameters are passed as a dict.
            assert params["q"] == "sleep anxiety"
            assert params["organization_id"] == org_id

    async def test_ranks_with_ts_rank_cd(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        await repo.search_across(org_id, "hello")

        for call in mock_session.execute.await_args_list:
            sql = str(call.args[0])
            assert "ts_rank_cd" in sql

    async def test_emits_headline_with_mark_tags(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        await repo.search_across(org_id, "hello")

        for call in mock_session.execute.await_args_list:
            sql = str(call.args[0])
            assert "ts_headline" in sql
            assert "StartSel=<mark>" in sql
            assert "StopSel=</mark>" in sql
            assert "MaxWords=30" in sql
            assert "MinWords=5" in sql

    async def test_covers_all_three_source_tables(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        await repo.search_across(org_id, "hello")

        sql_joined = " ".join(str(c.args[0]) for c in mock_session.execute.await_args_list)
        assert "FROM transcripts" in sql_joined
        assert "FROM session_recaps" in sql_joined
        assert "FROM sessions" in sql_joined

    async def test_scopes_to_organization(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        await repo.search_across(org_id, "hello")

        for call in mock_session.execute.await_args_list:
            sql = str(call.args[0])
            assert "u.organization_id = :organization_id" in sql

    async def test_optional_patient_filter_binds_none(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        await repo.search_across(org_id, "hello")

        for call in mock_session.execute.await_args_list:
            params = call.args[1]
            assert params["patient_id"] is None

    async def test_optional_patient_filter_binds_uuid(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        patient_id = uuid.uuid4()
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        await repo.search_across(org_id, "hello", patient_id=patient_id)

        for call in mock_session.execute.await_args_list:
            params = call.args[1]
            assert params["patient_id"] == patient_id
            sql = str(call.args[0])
            # Every query must respect the patient filter.
            assert ":patient_id IS NULL OR s.patient_id = :patient_id" in sql


class TestResultMapping:
    """Verify rows are materialized into SearchHit objects correctly."""

    async def test_hits_tag_source_per_query(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        s_id = uuid.uuid4()
        p_id = uuid.uuid4()
        now = datetime.now(UTC)

        transcript_row = _make_row(
            session_id=s_id,
            patient_id=p_id,
            patient_name="Alice",
            session_date=now,
            rank=0.1,
            snippet="transcript <mark>hit</mark>",
        )
        recap_row = _make_row(
            session_id=s_id,
            patient_id=p_id,
            patient_name="Alice",
            session_date=now,
            rank=0.2,
            snippet="recap <mark>hit</mark>",
        )
        notes_row = _make_row(
            session_id=s_id,
            patient_id=p_id,
            patient_name="Alice",
            session_date=now,
            rank=0.3,
            snippet="notes <mark>hit</mark>",
        )

        # Return in order: transcripts, recaps, sessions.
        mock_session.execute = AsyncMock(
            side_effect=[
                _result_with([transcript_row]),
                _result_with([recap_row]),
                _result_with([notes_row]),
            ]
        )

        hits = await repo.search_across(org_id, "hit")

        # Sort order is rank desc → notes(0.3), recap(0.2), transcript(0.1).
        assert [h.source for h in hits] == [
            SearchSource.NOTES,
            SearchSource.RECAP,
            SearchSource.TRANSCRIPT,
        ]
        assert [h.rank for h in hits] == [0.3, 0.2, 0.1]

    async def test_applies_limit_after_merge(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        s_id = uuid.uuid4()
        p_id = uuid.uuid4()
        now = datetime.now(UTC)

        rows = [
            _make_row(
                session_id=s_id,
                patient_id=p_id,
                patient_name="Alice",
                session_date=now,
                rank=float(i) / 10.0,
                snippet=f"<mark>hit {i}</mark>",
            )
            for i in range(5)
        ]
        mock_session.execute = AsyncMock(
            side_effect=[
                _result_with(rows),
                _result_with([]),
                _result_with([]),
            ]
        )

        hits = await repo.search_across(org_id, "hit", limit=3)
        assert len(hits) == 3
        # Limit is applied after the merge sort (rank desc), so we keep the
        # top-3 ranks regardless of which SQL returned them.
        assert [round(h.rank, 1) for h in hits] == [0.4, 0.3, 0.2]

    async def test_empty_when_no_matches(
        self,
        repo: SearchRepository,
        mock_session: AsyncMock,
        org_id: uuid.UUID,
    ) -> None:
        mock_session.execute = AsyncMock(return_value=_result_with([]))
        hits = await repo.search_across(org_id, "hit")
        assert hits == []
