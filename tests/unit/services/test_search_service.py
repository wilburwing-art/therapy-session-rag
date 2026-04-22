"""Unit tests for SearchService query validation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ValidationError
from src.models.domain.search import SearchHit, SearchSource
from src.services.search_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_QUERY_LENGTH,
    MIN_QUERY_LENGTH,
    SearchService,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock) -> SearchService:
    svc = SearchService(mock_session)
    # Replace the repository with a mock so we can assert on what the
    # service passes down after validation.
    svc._repo = MagicMock()
    svc._repo.search_across = AsyncMock(return_value=[])
    return svc


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


def _sample_hit() -> SearchHit:
    return SearchHit(
        session_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        patient_name="Test Patient",
        session_date=datetime.now(UTC),
        source=SearchSource.TRANSCRIPT,
        snippet="<mark>hello</mark> world",
        rank=0.5,
    )


class TestQueryValidation:
    """Tests for SearchService query-string validation."""

    async def test_rejects_empty_string(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await service.search_sessions(org_id, "")

    async def test_rejects_whitespace_only(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError):
            await service.search_sessions(org_id, "   \t  ")

    async def test_rejects_too_short(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        # MIN_QUERY_LENGTH is 2 → single-char should fail.
        assert MIN_QUERY_LENGTH == 2
        with pytest.raises(ValidationError):
            await service.search_sessions(org_id, "a")

    async def test_rejects_too_long(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        too_long = "x" * (MAX_QUERY_LENGTH + 1)
        with pytest.raises(ValidationError):
            await service.search_sessions(org_id, too_long)

    async def test_accepts_min_length(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        await service.search_sessions(org_id, "ab")
        service._repo.search_across.assert_awaited_once()
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["query"] == "ab"

    async def test_accepts_max_length(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        at_max = "x" * MAX_QUERY_LENGTH
        await service.search_sessions(org_id, at_max)
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["query"] == at_max

    async def test_trims_surrounding_whitespace(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        await service.search_sessions(org_id, "  sleep anxiety  ")
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["query"] == "sleep anxiety"


class TestLimitValidation:
    """Tests for SearchService limit clamping."""

    async def test_default_limit_when_unspecified(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        await service.search_sessions(org_id, "hello")
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["limit"] == DEFAULT_LIMIT

    async def test_clamps_limit_below_one(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        await service.search_sessions(org_id, "hello", limit=0)
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["limit"] == 1

    async def test_clamps_limit_above_max(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        await service.search_sessions(org_id, "hello", limit=9999)
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["limit"] == MAX_LIMIT

    async def test_passes_in_range_limit_through(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        await service.search_sessions(org_id, "hello", limit=7)
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["limit"] == 7


class TestForwardsToRepository:
    """Tests that validated args are forwarded correctly to the repo."""

    async def test_forwards_patient_filter(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        patient_id = uuid.uuid4()
        await service.search_sessions(
            org_id,
            "sleep",
            patient_id=patient_id,
        )
        kwargs = service._repo.search_across.await_args.kwargs
        assert kwargs["organization_id"] == org_id
        assert kwargs["patient_id"] == patient_id

    async def test_returns_repo_results(
        self, service: SearchService, org_id: uuid.UUID
    ) -> None:
        hit = _sample_hit()
        service._repo.search_across = AsyncMock(return_value=[hit])
        result = await service.search_sessions(org_id, "hello")
        assert result == [hit]
