"""Tests for chat service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.vector_search_repo import ChunkSearchResult
from src.services.chat_service import ChatService, ChatServiceError
from src.services.claude_client import ChatResponse as ClaudeChatResponse
from src.services.claude_client import ClaudeError, Message
from src.services.embedding_client import EmbeddingError, EmbeddingResult


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create mock database session."""
    return MagicMock()


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.openai_api_key = "test-key"
    settings.anthropic_api_key = "test-key"
    return settings


@pytest.fixture
def chat_service(
    mock_db_session: MagicMock,
    mock_settings: MagicMock,
) -> ChatService:
    """Create chat service with mocks."""
    return ChatService(
        db_session=mock_db_session,
        settings=mock_settings,
    )


@pytest.fixture
def sample_chunk() -> MagicMock:
    """Create a sample chunk."""
    chunk = MagicMock()
    chunk.id = uuid.uuid4()
    chunk.session_id = uuid.uuid4()
    chunk.content = "Patient discussed feeling anxious about work deadlines."
    chunk.start_time = 120.5
    chunk.speaker = "Speaker 0"
    return chunk


@pytest.fixture
def sample_search_result(sample_chunk: MagicMock) -> ChunkSearchResult:
    """Create a sample search result."""
    return ChunkSearchResult(chunk=sample_chunk, score=0.85)


class TestChat:
    """Tests for chat method."""

    @pytest.mark.asyncio
    async def test_generates_response_with_context(
        self,
        chat_service: ChatService,
        sample_search_result: ChunkSearchResult,
    ) -> None:
        """Test generating response with context from sessions."""
        patient_id = uuid.uuid4()

        # Mock embedding client
        chat_service._embedding_client = MagicMock()
        chat_service._embedding_client.embed_text = AsyncMock(
            return_value=EmbeddingResult(
                text="test query",
                embedding=[0.1] * 1536,
                model="text-embedding-3-small",
                token_count=5,
            )
        )

        # Mock vector search
        chat_service.vector_search.search_similar = AsyncMock(
            return_value=[sample_search_result]
        )

        # Mock Claude client
        chat_service._claude_client = MagicMock()
        chat_service._claude_client.chat = AsyncMock(
            return_value=ClaudeChatResponse(
                content="Based on your sessions, you mentioned feeling anxious about work deadlines.",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=50,
            )
        )
        chat_service._claude_client.create_rag_system_prompt = MagicMock(
            return_value="System prompt with context"
        )

        # Execute
        response = await chat_service.chat(
            patient_id=patient_id,
            message="What have I discussed about work stress?",
        )

        # Verify
        assert response.response is not None
        assert len(response.sources) == 1
        assert response.sources[0].relevance_score == 0.85
        assert response.conversation_id is not None

    @pytest.mark.asyncio
    async def test_handles_no_context(self, chat_service: ChatService) -> None:
        """Test handling when no relevant context is found."""
        patient_id = uuid.uuid4()

        # Mock embedding client
        chat_service._embedding_client = MagicMock()
        chat_service._embedding_client.embed_text = AsyncMock(
            return_value=EmbeddingResult(
                text="test query",
                embedding=[0.1] * 1536,
                model="text-embedding-3-small",
                token_count=5,
            )
        )

        # Mock vector search - no results
        chat_service.vector_search.search_similar = AsyncMock(return_value=[])

        # Mock Claude client
        chat_service._claude_client = MagicMock()
        chat_service._claude_client.chat = AsyncMock(
            return_value=ClaudeChatResponse(
                content="I don't have relevant context to answer that question.",
                model="claude-sonnet-4-20250514",
                input_tokens=50,
                output_tokens=20,
            )
        )

        # Execute
        response = await chat_service.chat(
            patient_id=patient_id,
            message="What about something unrelated?",
        )

        # Verify
        assert response.response is not None
        assert len(response.sources) == 0

    @pytest.mark.asyncio
    async def test_includes_conversation_history(
        self,
        chat_service: ChatService,
        sample_search_result: ChunkSearchResult,
    ) -> None:
        """Test that conversation history is included."""
        patient_id = uuid.uuid4()

        # Mock embedding client
        chat_service._embedding_client = MagicMock()
        chat_service._embedding_client.embed_text = AsyncMock(
            return_value=EmbeddingResult(
                text="test",
                embedding=[0.1] * 1536,
                model="text-embedding-3-small",
                token_count=5,
            )
        )

        # Mock vector search
        chat_service.vector_search.search_similar = AsyncMock(
            return_value=[sample_search_result]
        )

        # Mock Claude client
        chat_service._claude_client = MagicMock()
        chat_service._claude_client.chat = AsyncMock(
            return_value=ClaudeChatResponse(
                content="Follow-up response",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=50,
            )
        )
        chat_service._claude_client.create_rag_system_prompt = MagicMock(
            return_value="System prompt"
        )

        # Execute with history
        history = [
            Message(role="user", content="Previous question"),
            Message(role="assistant", content="Previous answer"),
        ]

        await chat_service.chat(
            patient_id=patient_id,
            message="Follow up question",
            conversation_history=history,
        )

        # Verify history was passed
        call_kwargs = chat_service._claude_client.chat.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 3  # 2 history + 1 new
        assert messages[0].content == "Previous question"
        assert messages[1].content == "Previous answer"
        assert messages[2].content == "Follow up question"

    @pytest.mark.asyncio
    async def test_handles_embedding_error(self, chat_service: ChatService) -> None:
        """Test handling of embedding errors."""
        patient_id = uuid.uuid4()

        # Mock embedding client to fail
        chat_service._embedding_client = MagicMock()
        chat_service._embedding_client.embed_text = AsyncMock(
            side_effect=EmbeddingError("API error")
        )

        # Execute and verify
        with pytest.raises(ChatServiceError) as exc_info:
            await chat_service.chat(
                patient_id=patient_id,
                message="Test message",
            )

        assert "Failed to process query" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handles_claude_error(
        self,
        chat_service: ChatService,
        sample_search_result: ChunkSearchResult,
    ) -> None:
        """Test handling of Claude errors."""
        patient_id = uuid.uuid4()

        # Mock embedding client
        chat_service._embedding_client = MagicMock()
        chat_service._embedding_client.embed_text = AsyncMock(
            return_value=EmbeddingResult(
                text="test",
                embedding=[0.1] * 1536,
                model="text-embedding-3-small",
                token_count=5,
            )
        )

        # Mock vector search
        chat_service.vector_search.search_similar = AsyncMock(
            return_value=[sample_search_result]
        )

        # Mock Claude client to fail
        chat_service._claude_client = MagicMock()
        chat_service._claude_client.chat = AsyncMock(
            side_effect=ClaudeError("API error")
        )
        chat_service._claude_client.create_rag_system_prompt = MagicMock(
            return_value="System prompt"
        )

        # Execute and verify
        with pytest.raises(ChatServiceError) as exc_info:
            await chat_service.chat(
                patient_id=patient_id,
                message="Test message",
            )

        assert "Failed to generate response" in str(exc_info.value)


class TestSourceCitations:
    """Tests for source citation generation."""

    @pytest.mark.asyncio
    async def test_includes_speaker_info(
        self,
        chat_service: ChatService,
    ) -> None:
        """Test that speaker info is included in sources."""
        patient_id = uuid.uuid4()

        # Create chunk with speaker info
        chunk = MagicMock()
        chunk.id = uuid.uuid4()
        chunk.session_id = uuid.uuid4()
        chunk.content = "Test content"
        chunk.start_time = 60.0
        chunk.speaker = "Speaker 1"

        search_result = ChunkSearchResult(chunk=chunk, score=0.9)

        # Mock clients
        chat_service._embedding_client = MagicMock()
        chat_service._embedding_client.embed_text = AsyncMock(
            return_value=EmbeddingResult(
                text="test",
                embedding=[0.1] * 1536,
                model="text-embedding-3-small",
                token_count=5,
            )
        )
        chat_service.vector_search.search_similar = AsyncMock(
            return_value=[search_result]
        )
        chat_service._claude_client = MagicMock()
        chat_service._claude_client.chat = AsyncMock(
            return_value=ClaudeChatResponse(
                content="Response",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=50,
            )
        )
        chat_service._claude_client.create_rag_system_prompt = MagicMock(
            return_value="System prompt"
        )

        # Execute
        response = await chat_service.chat(
            patient_id=patient_id,
            message="Test query",
        )

        # Verify source has speaker info
        assert len(response.sources) == 1
        assert response.sources[0].speaker == "Speaker 1"
        assert response.sources[0].start_time == 60.0


class TestGetPatientSessionCount:
    """Tests for get_patient_session_count method."""

    @pytest.mark.asyncio
    async def test_returns_session_count(self, chat_service: ChatService) -> None:
        """Test getting session count."""
        patient_id = uuid.uuid4()
        session_ids = [uuid.uuid4() for _ in range(3)]

        chat_service.vector_search.get_sessions_with_embeddings = AsyncMock(
            return_value=session_ids
        )

        count = await chat_service.get_patient_session_count(patient_id)

        assert count == 3


class TestGetChunkCount:
    """Tests for get_chunk_count method."""

    @pytest.mark.asyncio
    async def test_returns_chunk_count(self, chat_service: ChatService) -> None:
        """Test getting chunk count."""
        patient_id = uuid.uuid4()

        chat_service.vector_search.get_chunk_count_by_patient = AsyncMock(
            return_value=25
        )

        count = await chat_service.get_chunk_count(patient_id)

        assert count == 25


class TestNoContextSystemPrompt:
    """Tests for no-context system prompt."""

    def test_prompt_is_supportive(self, chat_service: ChatService) -> None:
        """Test that no-context prompt is supportive."""
        prompt = chat_service._get_no_context_system_prompt()

        assert "supportive" in prompt.lower()
        assert "therapist" in prompt.lower()
