"""Embedding stage - wraps EmbeddingClient for batch embedding."""

from __future__ import annotations

from typing import Any

from src.services.embedding_client import EmbeddingClient


async def embed_chunks(
    client: EmbeddingClient,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate embeddings for chunk texts.

    Returns serializable dicts suitable for JSON caching.
    """
    texts = [c["content"] for c in chunks]
    if not texts:
        return []

    results = await client.embed_batch(texts)

    return [
        {
            "text": r.text,
            "embedding": r.embedding,
            "model": r.model,
            "token_count": r.token_count,
        }
        for r in results
    ]
