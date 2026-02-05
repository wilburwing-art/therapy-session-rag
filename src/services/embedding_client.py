"""OpenAI embeddings client for generating text embeddings."""

import asyncio
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI, RateLimitError

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Error from embedding API."""

    def __init__(self, message: str, is_retryable: bool = False) -> None:
        super().__init__(message)
        self.is_retryable = is_retryable


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    text: str
    embedding: list[float]
    model: str
    token_count: int


class EmbeddingClient:
    """Client for OpenAI embeddings API.

    Provides methods for generating embeddings with automatic
    rate limit handling and batch processing.
    """

    DEFAULT_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSION = 1536
    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # seconds
    MAX_BATCH_SIZE = 100  # OpenAI limit

    def __init__(
        self,
        settings: Settings | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize embedding client.

        Args:
            settings: Application settings. If None, loads from environment.
            model: OpenAI embedding model to use. Defaults to text-embedding-3-small.
        """
        self.settings = settings or get_settings()
        self.model = model or self.DEFAULT_MODEL
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get or create OpenAI client (lazy initialization)."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._client

    async def close(self) -> None:
        """Close the client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with vector and metadata

        Raises:
            EmbeddingError: If embedding generation fails
        """
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts efficiently.

        Handles batching for large inputs and rate limit retries.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResult, one per input text

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not texts:
            return []

        # Split into batches if needed
        if len(texts) > self.MAX_BATCH_SIZE:
            results: list[EmbeddingResult] = []
            for i in range(0, len(texts), self.MAX_BATCH_SIZE):
                batch = texts[i : i + self.MAX_BATCH_SIZE]
                batch_results = await self._embed_batch_with_retry(batch)
                results.extend(batch_results)
            return results

        return await self._embed_batch_with_retry(texts)

    async def _embed_batch_with_retry(
        self, texts: list[str]
    ) -> list[EmbeddingResult]:
        """Embed a batch with retry logic.

        Args:
            texts: List of texts (max MAX_BATCH_SIZE)

        Returns:
            List of EmbeddingResult

        Raises:
            EmbeddingError: If all retries fail
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.client.embeddings.create(
                    input=texts,
                    model=self.model,
                )

                # Parse response - embeddings are returned in same order as input
                results: list[EmbeddingResult] = []
                for i, embedding_data in enumerate(response.data):
                    results.append(
                        EmbeddingResult(
                            text=texts[i],
                            embedding=embedding_data.embedding,
                            model=response.model,
                            token_count=response.usage.total_tokens // len(texts),
                        )
                    )

                return results

            except RateLimitError as e:
                last_error = e
                delay = self._calculate_backoff(attempt)
                logger.warning(
                    f"Rate limited by OpenAI, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
                continue

            except Exception as e:
                # For other errors, check if retryable
                error_msg = str(e)
                is_server_error = "500" in error_msg or "503" in error_msg

                if is_server_error and attempt < self.MAX_RETRIES - 1:
                    last_error = e
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        f"Server error, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.MAX_RETRIES}): {e}"
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable error
                raise EmbeddingError(
                    f"Failed to generate embeddings: {e}",
                    is_retryable=False,
                ) from e

        raise EmbeddingError(
            f"Failed to generate embeddings after {self.MAX_RETRIES} attempts: {last_error}",
            is_retryable=True,
        )

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        import random

        delay: float = self.BASE_DELAY * (2**attempt)
        # Add jitter (±25%)
        jitter: float = delay * 0.25 * (random.random() * 2 - 1)
        return delay + jitter

    def get_token_estimate(self, text: str) -> int:
        """Estimate token count for text.

        Uses simple heuristic of ~4 characters per token.
        For accurate counts, use tiktoken library.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Simple heuristic: ~4 chars per token
        return len(text) // 4 + 1
