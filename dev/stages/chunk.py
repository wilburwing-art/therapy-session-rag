"""Chunking stage - reuses EmbeddingService chunking logic."""

from __future__ import annotations

from typing import Any

from src.services.embedding_service import ChunkData, EmbeddingService

from dev.config import ChunkingConfig


def chunk_transcript(
    transcript_data: dict[str, Any],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    """Chunk a cached transcript using the existing chunking algorithm.

    Creates a minimal EmbeddingService instance just to reuse
    the chunk_transcript method (which is pure computation, no I/O).
    """
    # Create service with overridden chunk sizes
    service = EmbeddingService.__new__(EmbeddingService)
    service.TARGET_CHUNK_SIZE = config.target_chunk_size
    service.MAX_CHUNK_SIZE = config.max_chunk_size
    service.MIN_CHUNK_SIZE = config.min_chunk_size

    chunks: list[ChunkData] = service.chunk_transcript(
        full_text=transcript_data["full_text"],
        segments=transcript_data.get("segments", []),
    )

    return [
        {
            "content": c.content,
            "chunk_index": c.chunk_index,
            "start_time": c.start_time,
            "end_time": c.end_time,
            "speaker": c.speaker,
            "segment_indices": c.segment_indices,
        }
        for c in chunks
    ]
