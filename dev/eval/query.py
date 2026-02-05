"""RAG query evaluation tooling."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.user import User
from src.services.chat_service import ChatService
from src.services.claude_client import Message

from dev.config import ChatConfig
from dev.stages.load import DEV_PATIENT_EMAIL


@dataclass
class EvalResult:
    """Result of a RAG evaluation query."""

    query: str
    response: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    conversation_id: str = ""


async def get_dev_patient(db: AsyncSession) -> User:
    """Get the dev patient user."""
    result = await db.execute(
        select(User).where(User.email == DEV_PATIENT_EMAIL)
    )
    patient = result.scalar_one_or_none()
    if not patient:
        raise RuntimeError(
            "Dev patient not found. Run 'ingest' first to set up dev data."
        )
    return patient


async def evaluate_query(
    db: AsyncSession,
    query: str,
    config: ChatConfig,
    patient_id: uuid.UUID | None = None,
) -> EvalResult:
    """Run a RAG query and return results with sources."""
    if patient_id is None:
        patient = await get_dev_patient(db)
        patient_id = patient.id

    service = ChatService(db)
    response = await service.chat(
        patient_id=patient_id,
        message=query,
        top_k=config.top_k,
    )

    sources = [
        {
            "chunk_id": str(s.chunk_id),
            "content_preview": s.content_preview[:120],
            "relevance_score": s.relevance_score,
            "speaker": s.speaker,
            "start_time": s.start_time,
        }
        for s in response.sources
    ]

    return EvalResult(
        query=query,
        response=response.response,
        sources=sources,
        conversation_id=str(response.conversation_id),
    )


async def interactive_chat(
    db: AsyncSession,
    config: ChatConfig,
) -> None:
    """Interactive REPL for testing RAG queries."""
    patient = await get_dev_patient(db)
    service = ChatService(db)
    history: list[Message] = []
    show_sources = True

    session_count = await service.get_patient_session_count(patient.id)
    chunk_count = await service.get_chunk_count(patient.id)

    print(f"\nRAG Chat - {session_count} sessions, {chunk_count} chunks loaded")
    print("Commands: 'quit', 'sources' (toggle), 'clear' (history)")
    print("-" * 60)

    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not query:
            continue
        if query.lower() == "quit":
            break
        if query.lower() == "sources":
            show_sources = not show_sources
            print(f"Source display: {'on' if show_sources else 'off'}")
            continue
        if query.lower() == "clear":
            history.clear()
            print("Conversation history cleared.")
            continue

        response = await service.chat(
            patient_id=patient.id,
            message=query,
            conversation_history=history if history else None,
            top_k=config.top_k,
        )

        print(f"\n{response.response}")

        if show_sources and response.sources:
            print(f"\n--- {len(response.sources)} sources ---")
            for s in response.sources:
                score = f"{s.relevance_score:.2f}" if s.relevance_score else "?"
                preview = s.content_preview[:80]
                speaker = f" [{s.speaker}]" if s.speaker else ""
                print(f"  [{score}]{speaker} {preview}...")

        # Track history for follow-up questions
        history.append(Message(role="user", content=query))
        history.append(Message(role="assistant", content=response.response))
