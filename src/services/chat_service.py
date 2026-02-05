"""Service for RAG-based chat with therapy session context."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.models.domain.chat import ChatResponse, ChatSource
from src.repositories.vector_search_repo import VectorSearchRepository
from src.services.claude_client import ClaudeClient, ClaudeError, Message
from src.services.embedding_client import EmbeddingClient, EmbeddingError
from src.services.safety.guardrails import GuardrailAction, Guardrails

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    """Error during chat processing."""

    pass


class ChatService:
    """Service for RAG-based chat with therapy session context.

    Handles the workflow of:
    1. Generating embedding for user query
    2. Searching for relevant session chunks
    3. Building context for Claude
    4. Generating response with citations
    """

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.vector_search = VectorSearchRepository(db_session)
        self._embedding_client: EmbeddingClient | None = None
        self._claude_client: ClaudeClient | None = None
        self._guardrails: Guardrails | None = (
            Guardrails() if self.settings.safety_enabled else None
        )

    @property
    def embedding_client(self) -> EmbeddingClient:
        """Get or create embedding client (lazy initialization)."""
        if self._embedding_client is None:
            self._embedding_client = EmbeddingClient(settings=self.settings)
        return self._embedding_client

    @property
    def claude_client(self) -> ClaudeClient:
        """Get or create Claude client (lazy initialization)."""
        if self._claude_client is None:
            self._claude_client = ClaudeClient(settings=self.settings)
        return self._claude_client

    async def chat(
        self,
        patient_id: uuid.UUID,
        message: str,
        conversation_history: list[Message] | None = None,
        top_k: int = 5,
    ) -> ChatResponse:
        """Generate a chat response using RAG.

        Args:
            patient_id: The patient's ID (for security filtering)
            message: The user's message
            conversation_history: Previous messages in the conversation
            top_k: Number of context chunks to retrieve

        Returns:
            ChatResponse with content and source citations

        Raises:
            ChatServiceError: If chat processing fails
        """
        try:
            # Safety check on input
            prepend_crisis = False
            if self._guardrails:
                input_check = self._guardrails.check_input(message)
                if input_check.action == GuardrailAction.BLOCK:
                    logger.warning(
                        "Input blocked by guardrails: %s",
                        input_check.assessment.triggered_rules,
                    )
                    return ChatResponse(
                        response=(
                            "I'm not able to help with that request. "
                            "If you're in distress, please reach out to your "
                            "therapist or call 988 (Suicide & Crisis Lifeline)."
                        ),
                        conversation_id=uuid.uuid4(),
                        sources=[],
                    )
                if input_check.action == GuardrailAction.ESCALATE:
                    prepend_crisis = True

            # Generate embedding for the query
            query_embedding = await self._get_query_embedding(message)

            # Search for relevant chunks
            search_results = await self.vector_search.search_similar(
                query_embedding=query_embedding,
                patient_id=patient_id,
                top_k=top_k,
                min_score=0.5,  # Only include reasonably relevant results
            )

            # Build context and sources
            context_chunks: list[str] = []
            sources: list[ChatSource] = []

            for result in search_results:
                chunk = result.chunk

                # Build context string with metadata
                context_parts = []
                if chunk.speaker:
                    context_parts.append(f"[{chunk.speaker}]")
                if chunk.start_time is not None:
                    context_parts.append(f"(at {chunk.start_time:.1f}s)")
                context_parts.append(chunk.content)
                context_chunks.append(" ".join(context_parts))

                # Build source citation
                sources.append(
                    ChatSource(
                        session_id=chunk.session_id,
                        chunk_id=chunk.id,
                        content_preview=chunk.content[:200],
                        relevance_score=result.score,
                        start_time=chunk.start_time,
                        speaker=chunk.speaker,
                    )
                )

            # Build messages for Claude
            messages: list[Message] = []

            # Add conversation history if provided
            if conversation_history:
                messages.extend(conversation_history)

            # Add current message
            messages.append(Message(role="user", content=message))

            # Generate system prompt with context
            if context_chunks:
                system_prompt = self.claude_client.create_rag_system_prompt(
                    context_chunks
                )
            else:
                system_prompt = self._get_no_context_system_prompt()

            # Get response from Claude
            claude_response = await self.claude_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.7,
            )

            response_text = claude_response.content

            # Safety check on output
            if self._guardrails:
                output_check = self._guardrails.check_output(response_text)
                if output_check.action == GuardrailAction.BLOCK:
                    logger.warning(
                        "Output blocked by guardrails: %s",
                        output_check.assessment.triggered_rules,
                    )
                    response_text = (
                        "I generated a response that may not be appropriate. "
                        "Please consult your therapist or healthcare provider "
                        "for guidance on this topic."
                    )
                elif output_check.action == GuardrailAction.MODIFY and output_check.modified_text:
                    response_text = output_check.modified_text

            # Prepend crisis resources if escalation was triggered
            if prepend_crisis:
                response_text = Guardrails.prepend_crisis_resources(response_text)

            # Generate conversation ID
            conversation_id = uuid.uuid4()

            return ChatResponse(
                response=response_text,
                conversation_id=conversation_id,
                sources=sources,
            )

        except EmbeddingError as e:
            logger.error(f"Embedding error in chat: {e}")
            raise ChatServiceError(f"Failed to process query: {e}") from e

        except ClaudeError as e:
            logger.error(f"Claude error in chat: {e}")
            raise ChatServiceError(f"Failed to generate response: {e}") from e

        except Exception as e:
            logger.exception(f"Unexpected error in chat: {e}")
            raise ChatServiceError(f"Chat failed: {e}") from e

    async def _get_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for a search query.

        Args:
            query: The query text

        Returns:
            Embedding vector
        """
        result = await self.embedding_client.embed_text(query)
        return result.embedding

    def _get_no_context_system_prompt(self) -> str:
        """Get system prompt when no context is available."""
        return """You are a supportive AI assistant helping a patient with their therapy journey.

Unfortunately, I don't have access to relevant information from your therapy sessions to answer this specific question.

Please respond by:
1. Acknowledging that you don't have relevant context from their sessions
2. Suggesting they rephrase their question or ask about something else
3. Reminding them they can always discuss questions with their therapist

Be warm, supportive, and helpful despite the limitation."""

    async def get_patient_session_count(self, patient_id: uuid.UUID) -> int:
        """Get the number of sessions with embeddings for a patient.

        Args:
            patient_id: The patient's ID

        Returns:
            Number of sessions with searchable embeddings
        """
        sessions = await self.vector_search.get_sessions_with_embeddings(patient_id)
        return len(sessions)

    async def get_chunk_count(self, patient_id: uuid.UUID) -> int:
        """Get total chunk count for a patient.

        Args:
            patient_id: The patient's ID

        Returns:
            Total number of searchable chunks
        """
        return await self.vector_search.get_chunk_count_by_patient(patient_id)
