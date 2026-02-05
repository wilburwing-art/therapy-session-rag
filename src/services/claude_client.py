"""Claude client for chat completions."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from anthropic import AsyncAnthropic, RateLimitError
from anthropic.types import MessageParam, TextBlock

from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ClaudeError(Exception):
    """Error from Claude API."""

    def __init__(self, message: str, is_retryable: bool = False) -> None:
        super().__init__(message)
        self.is_retryable = is_retryable


@dataclass
class Message:
    """A chat message."""

    role: Literal["user", "assistant"]
    content: str


@dataclass
class ChatResponse:
    """Response from Claude chat completion."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None = None


@dataclass
class ChatRequest:
    """Request for Claude chat completion."""

    messages: list[Message]
    system_prompt: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.7


class ClaudeClient:
    """Client for Claude API chat completions.

    Provides methods for generating chat responses with automatic
    rate limit handling.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_RETRIES = 5
    BASE_DELAY = 1.0  # seconds

    def __init__(
        self,
        settings: Settings | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize Claude client.

        Args:
            settings: Application settings. If None, loads from environment.
            model: Claude model to use. Defaults to claude-sonnet-4-20250514.
        """
        self.settings = settings or get_settings()
        self.model = model or self.DEFAULT_MODEL
        self._client: AsyncAnthropic | None = None

    @property
    def client(self) -> AsyncAnthropic:
        """Get or create Anthropic client (lazy initialization)."""
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    async def close(self) -> None:
        """Close the client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """Generate a chat response.

        Args:
            messages: List of conversation messages
            system_prompt: Optional system prompt to guide responses
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)

        Returns:
            ChatResponse with generated content

        Raises:
            ClaudeError: If chat completion fails
        """
        request = ChatRequest(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return await self._chat_with_retry(request)

    async def _chat_with_retry(self, request: ChatRequest) -> ChatResponse:
        """Execute chat with retry logic.

        Args:
            request: The chat request

        Returns:
            ChatResponse

        Raises:
            ClaudeError: If all retries fail
        """
        last_error: Exception | None = None

        # Convert messages to Anthropic format
        anthropic_messages: list[MessageParam] = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=request.max_tokens,
                    system=request.system_prompt or "",
                    messages=anthropic_messages,
                    temperature=request.temperature,
                )

                # Extract content from response
                content = ""
                if response.content and isinstance(response.content[0], TextBlock):
                    content = response.content[0].text

                return ChatResponse(
                    content=content,
                    model=response.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    stop_reason=response.stop_reason,
                )

            except RateLimitError as e:
                last_error = e
                delay = self._calculate_backoff(attempt)
                logger.warning(
                    f"Rate limited by Claude, retrying in {delay:.1f}s "
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
                raise ClaudeError(
                    f"Failed to get chat response: {e}",
                    is_retryable=False,
                ) from e

        raise ClaudeError(
            f"Failed to get chat response after {self.MAX_RETRIES} attempts: {last_error}",
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

    def create_rag_system_prompt(self, context_chunks: list[str]) -> str:
        """Create a system prompt for RAG-based responses.

        Args:
            context_chunks: List of relevant context chunks

        Returns:
            System prompt string
        """
        context_text = "\n\n---\n\n".join(context_chunks)

        return f"""You are a supportive AI assistant helping a patient reflect on their therapy sessions. You have access to transcripts from their past therapy sessions.

IMPORTANT GUIDELINES:
1. Be warm, empathetic, and supportive in your responses
2. Only reference information from the provided context
3. If the context doesn't contain relevant information, say so honestly
4. Never make up or assume information not in the context
5. Respect the therapeutic nature of the content
6. Encourage the patient to discuss any concerns with their therapist
7. Do not provide medical advice or diagnoses

CONTEXT FROM THERAPY SESSIONS:
{context_text}

When answering questions:
- Cite specific parts of the sessions when relevant
- Help the patient connect insights across sessions
- Maintain a supportive, non-judgmental tone
- If uncertain, acknowledge the limitation"""
