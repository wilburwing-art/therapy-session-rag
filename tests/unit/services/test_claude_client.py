"""Tests for Claude client."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from anthropic import RateLimitError
from anthropic.types import TextBlock

from src.services.claude_client import (
    ChatResponse,
    ClaudeClient,
    ClaudeError,
    Message,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.anthropic_api_key = "test-api-key"
    return settings


@pytest.fixture
def claude_client(mock_settings: MagicMock) -> ClaudeClient:
    """Create Claude client with mocked settings."""
    return ClaudeClient(settings=mock_settings)


def create_mock_response(
    content: str = "Test response",
    model: str = "claude-sonnet-4-20250514",
    input_tokens: int = 10,
    output_tokens: int = 20,
    stop_reason: str = "end_turn",
) -> MagicMock:
    """Create a mock Anthropic response."""
    response = MagicMock()
    response.model = model
    response.stop_reason = stop_reason

    # Create a real TextBlock for isinstance check to work
    text_block = TextBlock(type="text", text=content)
    response.content = [text_block]

    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens

    return response


class TestClaudeClientInit:
    """Tests for ClaudeClient initialization."""

    def test_initializes_with_default_model(
        self, claude_client: ClaudeClient
    ) -> None:
        """Test client initializes with default model."""
        assert claude_client.model == "claude-sonnet-4-20250514"

    def test_initializes_with_custom_model(self, mock_settings: MagicMock) -> None:
        """Test client can use custom model."""
        client = ClaudeClient(
            settings=mock_settings,
            model="claude-3-opus-20240229",
        )
        assert client.model == "claude-3-opus-20240229"


class TestChat:
    """Tests for chat method."""

    @pytest.mark.asyncio
    async def test_generates_response(self, claude_client: ClaudeClient) -> None:
        """Test generating a chat response."""
        mock_response = create_mock_response(content="Hello there!")

        claude_client._client = MagicMock()
        claude_client._client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        response = await claude_client.chat(messages)

        assert isinstance(response, ChatResponse)
        assert response.content == "Hello there!"
        assert response.model == "claude-sonnet-4-20250514"
        assert response.input_tokens == 10
        assert response.output_tokens == 20

    @pytest.mark.asyncio
    async def test_passes_system_prompt(self, claude_client: ClaudeClient) -> None:
        """Test system prompt is passed to API."""
        mock_response = create_mock_response()

        claude_client._client = MagicMock()
        claude_client._client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await claude_client.chat(
            messages,
            system_prompt="You are a helpful assistant.",
        )

        call_kwargs = claude_client._client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_uses_temperature(self, claude_client: ClaudeClient) -> None:
        """Test temperature is passed to API."""
        mock_response = create_mock_response()

        claude_client._client = MagicMock()
        claude_client._client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await claude_client.chat(messages, temperature=0.5)

        call_kwargs = claude_client._client.messages.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5


class TestRetryLogic:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, claude_client: ClaudeClient) -> None:
        """Test retries on rate limit error."""
        mock_response = create_mock_response()
        call_count = 0

        async def mock_create(**_kwargs: dict) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RateLimitError(
                    "Rate limit exceeded",
                    response=MagicMock(status_code=429),
                    body=None,
                )
            return mock_response

        claude_client._client = MagicMock()
        claude_client._client.messages.create = mock_create
        claude_client.BASE_DELAY = 0.01  # Fast retries for testing

        messages = [Message(role="user", content="Hello")]
        response = await claude_client.chat(messages)

        assert call_count == 3
        assert response.content == "Test response"

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self, claude_client: ClaudeClient) -> None:
        """Test raises error after max retries exhausted."""

        async def mock_create(**_kwargs: dict) -> MagicMock:
            raise RateLimitError(
                "Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            )

        claude_client._client = MagicMock()
        claude_client._client.messages.create = mock_create
        claude_client.BASE_DELAY = 0.01
        claude_client.MAX_RETRIES = 2

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(ClaudeError) as exc_info:
            await claude_client.chat(messages)

        assert exc_info.value.is_retryable is True

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(
        self, claude_client: ClaudeClient
    ) -> None:
        """Test non-retryable errors raise immediately."""

        async def mock_create(**_kwargs: dict) -> MagicMock:
            raise ValueError("Invalid request")

        claude_client._client = MagicMock()
        claude_client._client.messages.create = mock_create

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(ClaudeError) as exc_info:
            await claude_client.chat(messages)

        assert exc_info.value.is_retryable is False


class TestBackoff:
    """Tests for backoff calculation."""

    def test_backoff_increases_exponentially(
        self, claude_client: ClaudeClient
    ) -> None:
        """Test backoff delay increases exponentially."""
        from unittest.mock import patch

        with patch("random.random", return_value=0.5):
            delay_0 = claude_client._calculate_backoff(0)
            delay_1 = claude_client._calculate_backoff(1)
            delay_2 = claude_client._calculate_backoff(2)

        assert delay_1 > delay_0
        assert delay_2 > delay_1


class TestRAGSystemPrompt:
    """Tests for RAG system prompt generation."""

    def test_creates_system_prompt_with_context(
        self, claude_client: ClaudeClient
    ) -> None:
        """Test system prompt includes context."""
        chunks = [
            "Patient discussed feeling anxious about work.",
            "Therapist suggested breathing exercises.",
        ]

        prompt = claude_client.create_rag_system_prompt(chunks)

        assert "Patient discussed feeling anxious" in prompt
        assert "breathing exercises" in prompt
        assert "supportive" in prompt.lower()
        assert "empathetic" in prompt.lower()

    def test_system_prompt_includes_guidelines(
        self, claude_client: ClaudeClient
    ) -> None:
        """Test system prompt includes safety guidelines."""
        prompt = claude_client.create_rag_system_prompt(["test context"])

        assert "therapist" in prompt.lower()
        assert "medical advice" in prompt.lower()


class TestMessage:
    """Tests for Message dataclass."""

    def test_creates_message(self) -> None:
        """Test Message creation."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"


class TestChatResponse:
    """Tests for ChatResponse dataclass."""

    def test_creates_chat_response(self) -> None:
        """Test ChatResponse creation."""
        response = ChatResponse(
            content="Test response",
            model="claude-sonnet-4-20250514",
            input_tokens=10,
            output_tokens=20,
            stop_reason="end_turn",
        )

        assert response.content == "Test response"
        assert response.input_tokens == 10
        assert response.output_tokens == 20


class TestClaudeError:
    """Tests for ClaudeError exception."""

    def test_creates_error_with_retryable_flag(self) -> None:
        """Test ClaudeError includes retryable flag."""
        error = ClaudeError("test error", is_retryable=True)
        assert str(error) == "test error"
        assert error.is_retryable is True

    def test_default_not_retryable(self) -> None:
        """Test default is not retryable."""
        error = ClaudeError("test error")
        assert error.is_retryable is False
