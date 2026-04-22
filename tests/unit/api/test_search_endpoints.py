"""Unit tests for GET /api/v1/search."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth
from src.api.v1.endpoints.search import get_search_service, router
from src.core.database import get_db_session
from src.core.exceptions import setup_exception_handlers
from src.models.domain.search import SearchHit, SearchSource


@pytest.fixture
def mock_auth_context() -> MagicMock:
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = uuid.uuid4()
    ctx.api_key_name = "test-key"
    return ctx


@pytest.fixture
def mock_search_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def app(
    mock_auth_context: MagicMock,
    mock_search_service: MagicMock,
) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/search")
    setup_exception_handlers(test_app)

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_search_service] = lambda: mock_search_service
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture
def no_auth_app(mock_search_service: MagicMock) -> FastAPI:
    """App variant that leaves auth wired to the real dependency."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/search")
    setup_exception_handlers(test_app)
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_search_service] = lambda: mock_search_service
    return test_app


@pytest.fixture
def no_auth_client(no_auth_app: FastAPI) -> TestClient:
    return TestClient(no_auth_app)


def _hit(*, source: SearchSource = SearchSource.TRANSCRIPT) -> SearchHit:
    return SearchHit(
        session_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        patient_name="Alice",
        session_date=datetime.now(UTC),
        source=source,
        snippet="<mark>sleep</mark> anxiety",
        rank=0.5,
    )


class TestSearchEndpoint:
    """Tests for GET /search."""

    def test_returns_200_with_list(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
        mock_auth_context: MagicMock,
    ) -> None:
        hits = [_hit(source=SearchSource.TRANSCRIPT), _hit(source=SearchSource.NOTES)]
        mock_search_service.search_sessions = AsyncMock(return_value=hits)

        response = client.get("/search?q=sleep")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["source"] in {"transcript", "recap", "notes"}
        assert "<mark>" in body[0]["snippet"]

        mock_search_service.search_sessions.assert_awaited_once()
        kwargs = mock_search_service.search_sessions.await_args.kwargs
        assert kwargs["organization_id"] == mock_auth_context.organization_id
        assert kwargs["query"] == "sleep"
        assert kwargs["patient_id"] is None

    def test_returns_200_with_empty_list(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        mock_search_service.search_sessions = AsyncMock(return_value=[])
        response = client.get("/search?q=nothing")
        assert response.status_code == 200
        assert response.json() == []

    def test_forwards_patient_id_filter(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        patient_id = uuid.uuid4()
        mock_search_service.search_sessions = AsyncMock(return_value=[])

        response = client.get(f"/search?q=sleep&patient_id={patient_id}")

        assert response.status_code == 200
        kwargs = mock_search_service.search_sessions.await_args.kwargs
        assert kwargs["patient_id"] == patient_id

    def test_forwards_limit(
        self,
        client: TestClient,
        mock_search_service: MagicMock,
    ) -> None:
        mock_search_service.search_sessions = AsyncMock(return_value=[])

        response = client.get("/search?q=sleep&limit=5")

        assert response.status_code == 200
        kwargs = mock_search_service.search_sessions.await_args.kwargs
        assert kwargs["limit"] == 5

    def test_422_when_query_missing(self, client: TestClient) -> None:
        response = client.get("/search")
        assert response.status_code == 422

    def test_422_when_query_empty(self, client: TestClient) -> None:
        response = client.get("/search?q=")
        assert response.status_code == 422

    def test_422_when_query_too_short(self, client: TestClient) -> None:
        response = client.get("/search?q=a")
        assert response.status_code == 422

    def test_422_when_query_too_long(self, client: TestClient) -> None:
        too_long = "x" * 201
        response = client.get(f"/search?q={too_long}")
        assert response.status_code == 422

    def test_422_when_limit_below_min(self, client: TestClient) -> None:
        response = client.get("/search?q=hello&limit=0")
        assert response.status_code == 422

    def test_422_when_limit_above_max(self, client: TestClient) -> None:
        response = client.get("/search?q=hello&limit=999")
        assert response.status_code == 422

    def test_401_without_auth(self, no_auth_client: TestClient) -> None:
        """With no cookie and no API key, the shared Auth dep returns 401."""
        response = no_auth_client.get("/search?q=sleep")
        assert response.status_code == 401
