"""Retrieval-quality evaluation.

For each synthetic transcript:
  1. Chunk the transcript with the real EmbeddingService.chunk_transcript
     (pure function, no DB).
  2. Embed chunks via the FakeEmbeddingClient (deterministic).
  3. Load chunks into a FakeVectorSearchRepo keyed by a stable patient UUID.
  4. For each test_query, embed it and retrieve top_k=3.
  5. Assert hit@3: at least one of the top 3 chunks contains one of the
     expected_chunk_substring_any.

Aggregate hit@3 across all queries across all fixtures must be >= 0.7.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from src.services.embedding_service import EmbeddingService
from tests.evaluation.conftest import (
    FakeEmbeddingClient,
    FakeVectorSearchRepo,
    StoredChunk,
    TranscriptFixture,
)

pytestmark = pytest.mark.evaluation


_TOP_K = 3
_HIT_AT_3_THRESHOLD = 0.7


# Stable per-fixture patient UUID so repeated test runs are reproducible.
def _patient_id_for(fixture_name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"eval.patient.{fixture_name}")


def _session_id_for(fixture_name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"eval.session.{fixture_name}")


def _chunk_service() -> EmbeddingService:
    """EmbeddingService instance with db_session=None (only chunk_transcript is used)."""
    # chunk_transcript is a pure method. Instantiate without touching db.
    return EmbeddingService.__new__(EmbeddingService)


async def _index_fixture(
    fixture: TranscriptFixture,
    embed_client: FakeEmbeddingClient,
    repo: FakeVectorSearchRepo,
) -> list[StoredChunk]:
    """Chunk, embed, and store a fixture; return stored chunks."""
    service = _chunk_service()
    chunks_data = service.chunk_transcript(
        full_text=fixture.full_text,
        segments=fixture.segments,
    )
    # If chunking yields nothing (shouldn't for our fixtures), fall back to
    # one chunk per segment so retrieval still has content to search.
    if not chunks_data:
        raise AssertionError(f"chunk_transcript returned no chunks for {fixture.name}")

    stored: list[StoredChunk] = []
    patient_id = _patient_id_for(fixture.name)
    session_id = _session_id_for(fixture.name)

    for cd in chunks_data:
        embedding = (await embed_client.embed_text(cd.content)).embedding
        stored.append(
            StoredChunk(
                id=uuid.uuid4(),
                session_id=session_id,
                content=cd.content,
                embedding=embedding,
                start_time=cd.start_time,
                end_time=cd.end_time,
                speaker=cd.speaker,
            )
        )

    repo.add_chunks(patient_id=patient_id, chunks=stored)
    return stored


def _hit(stored_results: list[Any], expected_substrings: list[str]) -> bool:
    """Return True iff any result chunk's content contains any expected substring."""
    lowered = [s.lower() for s in expected_substrings]
    for r in stored_results:
        content = r.chunk.content.lower()
        if any(sub in content for sub in lowered):
            return True
    return False


async def test_retrieval_hit_at_3(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_embedding_client: FakeEmbeddingClient,
    fake_vector_search_repo: FakeVectorSearchRepo,
) -> None:
    """Aggregate hit@3 across all test queries across all fixtures.

    Per-query assertion tolerates some misses but the aggregate must be
    >= _HIT_AT_3_THRESHOLD.
    """
    # Index every fixture into the same repo, each under its own patient_id.
    for fixture in all_transcript_fixtures:
        await _index_fixture(fixture, mock_embedding_client, fake_vector_search_repo)

    total_queries = 0
    hits = 0
    miss_report: list[str] = []

    for fixture in all_transcript_fixtures:
        patient_id = _patient_id_for(fixture.name)
        for tq in fixture.test_queries:
            total_queries += 1
            query = cast(str, tq["query"])
            expected = cast(list[str], tq["expected_chunk_substring_any"])

            q_embed = (await mock_embedding_client.embed_text(query)).embedding
            results = await fake_vector_search_repo.search_similar(
                query_embedding=q_embed,
                patient_id=patient_id,
                top_k=_TOP_K,
            )
            if _hit(results, expected):
                hits += 1
            else:
                top_contents = [
                    (r.chunk.content[:80].replace("\n", " "), round(r.score, 3)) for r in results
                ]
                miss_report.append(
                    f"[{fixture.name}] {query!r} expected-any={expected!r} top3={top_contents!r}"
                )

    assert total_queries > 0, "no queries were evaluated"
    rate = hits / total_queries
    print(f"\n[retrieval-eval] hit@{_TOP_K} = {hits}/{total_queries} ({rate:.0%})")

    if rate < _HIT_AT_3_THRESHOLD:
        detail = "\n  - ".join(miss_report)
        pytest.fail(
            f"hit@{_TOP_K} = {rate:.0%} below threshold "
            f"{_HIT_AT_3_THRESHOLD:.0%}\nMisses:\n  - {detail}"
        )


async def test_retrieval_isolates_by_patient(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_embedding_client: FakeEmbeddingClient,
    fake_vector_search_repo: FakeVectorSearchRepo,
) -> None:
    """A patient's search must not surface another patient's chunks."""
    # Use at least the first two fixtures; index each under its own patient.
    if len(all_transcript_fixtures) < 2:
        pytest.skip("need at least 2 fixtures")

    fx_a, fx_b = all_transcript_fixtures[0], all_transcript_fixtures[1]
    await _index_fixture(fx_a, mock_embedding_client, fake_vector_search_repo)
    await _index_fixture(fx_b, mock_embedding_client, fake_vector_search_repo)

    pid_a = _patient_id_for(fx_a.name)
    pid_b = _patient_id_for(fx_b.name)

    # Query with fixture B's topic label, but search under patient A.
    q_text = fx_b.topic_label
    q_embed = (await mock_embedding_client.embed_text(q_text)).embedding

    a_results = await fake_vector_search_repo.search_similar(
        query_embedding=q_embed,
        patient_id=pid_a,
        top_k=5,
    )
    b_results = await fake_vector_search_repo.search_similar(
        query_embedding=q_embed,
        patient_id=pid_b,
        top_k=5,
    )

    assert all(r.chunk.session_id == _session_id_for(fx_a.name) for r in a_results), (
        f"patient A search returned non-A chunks: {[r.chunk.session_id for r in a_results]}"
    )
    assert all(r.chunk.session_id == _session_id_for(fx_b.name) for r in b_results), (
        f"patient B search returned non-B chunks: {[r.chunk.session_id for r in b_results]}"
    )


async def test_retrieval_deterministic(
    all_transcript_fixtures: list[TranscriptFixture],
    mock_embedding_client: FakeEmbeddingClient,
) -> None:
    """Same query embed -> same vector on repeated calls."""
    text = all_transcript_fixtures[0].test_queries[0]["query"]
    e1 = (await mock_embedding_client.embed_text(text)).embedding
    e2 = (await mock_embedding_client.embed_text(text)).embedding
    assert e1 == e2, "embedding is not deterministic"
    assert len(e1) == FakeEmbeddingClient.EMBEDDING_DIMENSION
