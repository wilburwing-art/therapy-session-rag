"""Unit tests for Chat API endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.dependencies import get_api_key_auth, get_event_publisher
from src.api.v1.endpoints.chat import (
    get_chat_rate_limiter,
    get_chat_service,
    get_conversation_service,
    router,
)
from src.core.database import get_db_session
from src.core.exceptions import setup_exception_handlers
from src.models.db.conversation import Conversation
from src.models.domain.chat import ChatResponse, ChatSource
from src.services.chat_service import ChatServiceError
from src.services.rate_limiter import RateLimitExceeded


@pytest.fixture
def mock_auth_context() -> MagicMock:
    """Create a mock auth context."""
    ctx = MagicMock()
    ctx.api_key_id = uuid.uuid4()
    ctx.organization_id = uuid.uuid4()
    ctx.api_key_name = "test-key"
    return ctx


@pytest.fixture
def mock_chat_service() -> MagicMock:
    """Create a mock chat service."""
    return MagicMock()


@pytest.fixture
def mock_rate_limiter() -> MagicMock:
    """Create a mock rate limiter."""
    limiter = MagicMock()
    limiter.max_requests = 20
    # Default to allowing requests
    limiter.check_and_consume = AsyncMock(
        return_value={"current_count": 1, "remaining": 19, "reset_time": 3600}
    )
    limiter.get_remaining = AsyncMock(return_value=19)
    return limiter


@pytest.fixture
def mock_conversation_service(mock_auth_context: MagicMock) -> MagicMock:
    """Create a mock conversation service."""
    service = MagicMock()
    # Create a mock conversation
    mock_conversation = MagicMock(spec=Conversation)
    mock_conversation.id = uuid.uuid4()
    mock_conversation.patient_id = uuid.uuid4()
    mock_conversation.organization_id = mock_auth_context.organization_id
    mock_conversation.messages = []

    service.get_or_create_conversation = AsyncMock(
        return_value=(mock_conversation, True)
    )
    service.get_history_for_claude = MagicMock(return_value=[])
    service.add_user_message = AsyncMock()
    service.add_assistant_message = AsyncMock()
    service.generate_title = AsyncMock(return_value="Test conversation")
    service.list_conversations = AsyncMock(return_value=[])
    service.get_conversation = AsyncMock()
    return service


@pytest.fixture
def app(
    mock_auth_context: MagicMock,
    mock_chat_service: MagicMock,
    mock_conversation_service: MagicMock,
    mock_rate_limiter: MagicMock,
) -> FastAPI:
    """Create test app with mocked dependencies."""
    test_app = FastAPI()
    setup_exception_handlers(test_app)
    test_app.include_router(router, prefix="/chat")

    mock_events = MagicMock()
    mock_events.publish = AsyncMock(return_value=None)

    test_app.dependency_overrides[get_api_key_auth] = lambda: mock_auth_context
    test_app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    test_app.dependency_overrides[get_conversation_service] = lambda: mock_conversation_service
    test_app.dependency_overrides[get_chat_rate_limiter] = lambda: mock_rate_limiter
    test_app.dependency_overrides[get_event_publisher] = lambda: mock_events

    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def patient_id() -> uuid.UUID:
    """Create a test patient ID."""
    return uuid.uuid4()


def make_chat_response(
    response_text: str = "This is a response based on your therapy sessions.",
    sources: list[ChatSource] | None = None,
) -> ChatResponse:
    """Create a ChatResponse for testing."""
    if sources is None:
        sources = [
            ChatSource(
                session_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
                content_preview="Patient discussed feeling anxious...",
                relevance_score=0.85,
                start_time=120.5,
                speaker="Speaker 0",
            )
        ]
    return ChatResponse(
        response=response_text,
        conversation_id=uuid.uuid4(),
        sources=sources,
    )


class TestChatEndpoint:
    """Tests for POST /chat endpoint."""

    def test_chat_success(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test successful chat request."""
        mock_response = make_chat_response()
        mock_chat_service.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "What have we discussed about my anxiety?",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "sources" in data
        assert "conversation_id" in data
        mock_chat_service.chat.assert_called_once()

    def test_chat_with_conversation_id(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat with existing conversation ID."""
        mock_response = make_chat_response()
        mock_chat_service.chat = AsyncMock(return_value=mock_response)
        conversation_id = uuid.uuid4()

        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Follow up question",
                "conversation_id": str(conversation_id),
            },
        )

        assert response.status_code == 200
        mock_chat_service.chat.assert_called_once()

    def test_chat_with_custom_top_k(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat with custom top_k parameter."""
        mock_response = make_chat_response()
        mock_chat_service.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Test message",
                "top_k": 10,
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_chat_service.chat.call_args.kwargs
        assert call_kwargs["top_k"] == 10

    def test_chat_no_sources(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat response with no matching sources."""
        mock_response = make_chat_response(
            response_text="I don't have relevant context to answer that.",
            sources=[],
        )
        mock_chat_service.chat = AsyncMock(return_value=mock_response)

        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "What about something unrelated?",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sources"] == []

    def test_chat_service_error(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test handling of chat service errors."""
        mock_chat_service.chat = AsyncMock(
            side_effect=ChatServiceError("Failed to process query")
        )

        # The generic exception handler returns 500
        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Test message",
            },
        )

        assert response.status_code == 500


class TestChatRateLimiting:
    """Tests for chat rate limiting."""

    def test_chat_rate_limited(
        self,
        client: TestClient,
        mock_rate_limiter: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat returns 429 when rate limited."""
        mock_rate_limiter.check_and_consume = AsyncMock(
            side_effect=RateLimitExceeded(
                "Rate limit exceeded",
                remaining=0,
                reset_time=1800,
            )
        )

        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Test message",
            },
        )

        assert response.status_code == 429
        data = response.json()
        assert data["title"] == "Too Many Requests"
        assert data["retry_after"] == 1800

    def test_chat_consumes_rate_limit(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        mock_rate_limiter: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test that successful chat consumes rate limit."""
        mock_response = make_chat_response()
        mock_chat_service.chat = AsyncMock(return_value=mock_response)

        client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Test message",
            },
        )

        mock_rate_limiter.check_and_consume.assert_called_once_with(patient_id)


class TestChatEndpointValidation:
    """Tests for chat endpoint input validation."""

    def test_chat_empty_message(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat with empty message."""
        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "",
            },
        )

        assert response.status_code == 422

    def test_chat_message_too_long(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat with message exceeding max length."""
        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "x" * 4001,  # Max is 4000
            },
        )

        assert response.status_code == 422

    def test_chat_invalid_patient_id(
        self,
        client: TestClient,
    ) -> None:
        """Test chat with invalid patient ID."""
        response = client.post(
            "/chat",
            params={"patient_id": "not-a-uuid"},
            json={
                "message": "Test message",
            },
        )

        assert response.status_code == 422

    def test_chat_missing_patient_id(
        self,
        client: TestClient,
    ) -> None:
        """Test chat without patient ID."""
        response = client.post(
            "/chat",
            json={
                "message": "Test message",
            },
        )

        assert response.status_code == 422

    def test_chat_invalid_top_k_too_low(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat with top_k below minimum."""
        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Test message",
                "top_k": 0,
            },
        )

        assert response.status_code == 422

    def test_chat_invalid_top_k_too_high(
        self,
        client: TestClient,
        patient_id: uuid.UUID,
    ) -> None:
        """Test chat with top_k above maximum."""
        response = client.post(
            "/chat",
            params={"patient_id": str(patient_id)},
            json={
                "message": "Test message",
                "top_k": 11,
            },
        )

        assert response.status_code == 422


class TestSessionsCountEndpoint:
    """Tests for GET /chat/sessions-count endpoint."""

    def test_get_sessions_count(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting session count."""
        mock_chat_service.get_patient_session_count = AsyncMock(return_value=5)

        response = client.get(
            "/chat/sessions-count",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_count"] == 5
        mock_chat_service.get_patient_session_count.assert_called_once()

    def test_get_sessions_count_zero(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting session count when no sessions."""
        mock_chat_service.get_patient_session_count = AsyncMock(return_value=0)

        response = client.get(
            "/chat/sessions-count",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_count"] == 0


class TestChunksCountEndpoint:
    """Tests for GET /chat/chunks-count endpoint."""

    def test_get_chunks_count(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting chunk count."""
        mock_chat_service.get_chunk_count = AsyncMock(return_value=42)

        response = client.get(
            "/chat/chunks-count",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_count"] == 42
        mock_chat_service.get_chunk_count.assert_called_once()

    def test_get_chunks_count_zero(
        self,
        client: TestClient,
        mock_chat_service: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting chunk count when no chunks."""
        mock_chat_service.get_chunk_count = AsyncMock(return_value=0)

        response = client.get(
            "/chat/chunks-count",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chunk_count"] == 0


class TestRateLimitStatusEndpoint:
    """Tests for GET /chat/rate-limit endpoint."""

    def test_get_rate_limit_status(
        self,
        client: TestClient,
        mock_rate_limiter: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting rate limit status."""
        mock_rate_limiter.get_remaining = AsyncMock(return_value=15)

        response = client.get(
            "/chat/rate-limit",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["remaining"] == 15
        assert data["max_per_hour"] == 20
        mock_rate_limiter.get_remaining.assert_called_once_with(patient_id)

    def test_get_rate_limit_status_exhausted(
        self,
        client: TestClient,
        mock_rate_limiter: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting rate limit status when exhausted."""
        mock_rate_limiter.get_remaining = AsyncMock(return_value=0)

        response = client.get(
            "/chat/rate-limit",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["remaining"] == 0

    def test_get_rate_limit_status_full(
        self,
        client: TestClient,
        mock_rate_limiter: MagicMock,
        patient_id: uuid.UUID,
    ) -> None:
        """Test getting rate limit status when unused."""
        mock_rate_limiter.get_remaining = AsyncMock(return_value=20)

        response = client.get(
            "/chat/rate-limit",
            params={"patient_id": str(patient_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["remaining"] == 20
