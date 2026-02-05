"""Tests for embedding client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import RateLimitError

from src.services.embedding_client import (
    EmbeddingClient,
    EmbeddingError,
    EmbeddingResult,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.openai_api_key = "test-api-key"
    return settings


@pytest.fixture
def embedding_client(mock_settings: MagicMock) -> EmbeddingClient:
    """Create embedding client with mocked settings."""
    return EmbeddingClient(settings=mock_settings)


def create_mock_embedding_response(
    texts: list[str],
    model: str = "text-embedding-3-small",
) -> MagicMock:
    """Create a mock OpenAI embedding response."""
    response = MagicMock()
    response.model = model
    response.data = []
    response.usage = MagicMock()
    response.usage.total_tokens = len(texts) * 10

    for _ in texts:
        embedding_data = MagicMock()
        embedding_data.embedding = [0.1] * 1536
        response.data.append(embedding_data)

    return response


class TestEmbeddingClientInit:
    """Tests for EmbeddingClient initialization."""

    def test_initializes_with_default_model(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test client initializes with default model."""
        assert embedding_client.model == "text-embedding-3-small"

    def test_initializes_with_custom_model(self, mock_settings: MagicMock) -> None:
        """Test client can use custom model."""
        client = EmbeddingClient(
            settings=mock_settings,
            model="text-embedding-3-large",
        )
        assert client.model == "text-embedding-3-large"

    def test_has_correct_constants(self) -> None:
        """Test client has expected constants."""
        assert EmbeddingClient.EMBEDDING_DIMENSION == 1536
        assert EmbeddingClient.MAX_BATCH_SIZE == 100
        assert EmbeddingClient.MAX_RETRIES == 5


class TestEmbedText:
    """Tests for embed_text method."""

    @pytest.mark.asyncio
    async def test_embeds_single_text(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test embedding a single text."""
        mock_response = create_mock_embedding_response(["test text"])

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = AsyncMock(return_value=mock_response)
            embedding_client._client = mock_openai

            result = await embedding_client.embed_text("test text")

            assert isinstance(result, EmbeddingResult)
            assert result.text == "test text"
            assert len(result.embedding) == 1536
            assert result.model == "text-embedding-3-small"

    @pytest.mark.asyncio
    async def test_returns_embedding_result(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test returned EmbeddingResult has all fields."""
        mock_response = create_mock_embedding_response(["hello world"])

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = AsyncMock(return_value=mock_response)
            embedding_client._client = mock_openai

            result = await embedding_client.embed_text("hello world")

            assert result.text == "hello world"
            assert result.embedding is not None
            assert result.model is not None
            assert result.token_count > 0


class TestEmbedBatch:
    """Tests for embed_batch method."""

    @pytest.mark.asyncio
    async def test_embeds_multiple_texts(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test embedding multiple texts."""
        texts = ["text one", "text two", "text three"]
        mock_response = create_mock_embedding_response(texts)

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = AsyncMock(return_value=mock_response)
            embedding_client._client = mock_openai

            results = await embedding_client.embed_batch(texts)

            assert len(results) == 3
            assert results[0].text == "text one"
            assert results[1].text == "text two"
            assert results[2].text == "text three"

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_input(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test empty input returns empty list."""
        results = await embedding_client.embed_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_handles_large_batch(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test batching for inputs larger than MAX_BATCH_SIZE."""
        # Create 150 texts (> MAX_BATCH_SIZE of 100)
        texts = [f"text {i}" for i in range(150)]

        call_count = 0

        async def mock_create(**kwargs: dict) -> MagicMock:
            nonlocal call_count
            call_count += 1
            input_texts = kwargs.get("input", [])
            return create_mock_embedding_response(input_texts)  # type: ignore[arg-type]

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = mock_create
            embedding_client._client = mock_openai

            results = await embedding_client.embed_batch(texts)

            # Should have made 2 API calls (100 + 50)
            assert call_count == 2
            assert len(results) == 150


class TestRetryLogic:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test retries on rate limit error."""
        texts = ["test text"]
        mock_response = create_mock_embedding_response(texts)

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

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = mock_create
            embedding_client._client = mock_openai

            # Reduce delays for testing
            embedding_client.BASE_DELAY = 0.01

            results = await embedding_client.embed_batch(texts)

            assert call_count == 3
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test raises error after max retries exhausted."""
        texts = ["test text"]

        async def mock_create(**_kwargs: dict) -> MagicMock:
            raise RateLimitError(
                "Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            )

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = mock_create
            embedding_client._client = mock_openai

            # Reduce delays and retries for testing
            embedding_client.BASE_DELAY = 0.01
            embedding_client.MAX_RETRIES = 2

            with pytest.raises(EmbeddingError) as exc_info:
                await embedding_client.embed_batch(texts)

            assert exc_info.value.is_retryable is True
            assert "2 attempts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test non-retryable errors raise immediately."""
        texts = ["test text"]

        async def mock_create(**_kwargs: dict) -> MagicMock:
            raise ValueError("Invalid input")

        with patch.object(
            embedding_client, "_client", create=True
        ) as mock_openai:
            mock_openai.embeddings.create = mock_create
            embedding_client._client = mock_openai

            with pytest.raises(EmbeddingError) as exc_info:
                await embedding_client.embed_batch(texts)

            assert exc_info.value.is_retryable is False


class TestBackoff:
    """Tests for backoff calculation."""

    def test_backoff_increases_exponentially(
        self, embedding_client: EmbeddingClient
    ) -> None:
        """Test backoff delay increases exponentially."""
        # Get delays without jitter for comparison
        with patch("random.random", return_value=0.5):  # No jitter
            delay_0 = embedding_client._calculate_backoff(0)
            delay_1 = embedding_client._calculate_backoff(1)
            delay_2 = embedding_client._calculate_backoff(2)

        # Each delay should be ~2x the previous
        assert delay_1 > delay_0
        assert delay_2 > delay_1
        # Allow some tolerance for jitter
        assert 1.5 < delay_1 / delay_0 < 2.5
        assert 1.5 < delay_2 / delay_1 < 2.5


class TestTokenEstimate:
    """Tests for token estimation."""

    def test_estimates_tokens(self, embedding_client: EmbeddingClient) -> None:
        """Test token estimation."""
        # ~4 chars per token
        short_text = "hi"
        long_text = "a" * 100

        short_estimate = embedding_client.get_token_estimate(short_text)
        long_estimate = embedding_client.get_token_estimate(long_text)

        assert short_estimate >= 1
        assert long_estimate > short_estimate
        assert long_estimate >= 25  # 100 chars / 4 + 1


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_creates_embedding_result(self) -> None:
        """Test EmbeddingResult creation."""
        result = EmbeddingResult(
            text="test",
            embedding=[0.1, 0.2, 0.3],
            model="text-embedding-3-small",
            token_count=5,
        )

        assert result.text == "test"
        assert result.embedding == [0.1, 0.2, 0.3]
        assert result.model == "text-embedding-3-small"
        assert result.token_count == 5


class TestEmbeddingError:
    """Tests for EmbeddingError exception."""

    def test_creates_error_with_retryable_flag(self) -> None:
        """Test EmbeddingError includes retryable flag."""
        error = EmbeddingError("test error", is_retryable=True)
        assert str(error) == "test error"
        assert error.is_retryable is True

    def test_default_not_retryable(self) -> None:
        """Test default is not retryable."""
        error = EmbeddingError("test error")
        assert error.is_retryable is False
