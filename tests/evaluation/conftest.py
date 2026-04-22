"""Deterministic fixtures and fakes for the RAG evaluation harness.

These fakes replace the Claude API, OpenAI embeddings, and the pgvector
search repo with in-process, deterministic implementations so the
evaluation suite can run without any external services.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from src.services.claude_client import ChatResponse, Message

FIXTURES_DIR = Path(__file__).parent / "fixtures"

EMBEDDING_DIM = 1536


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


@dataclass
class TranscriptFixture:
    """A loaded fixture file for a single synthetic therapy session."""

    path: Path
    disclaimer: str
    topic_label: str
    full_text: str
    segments: list[dict[str, Any]]
    expected_recap: dict[str, Any]
    test_queries: list[dict[str, Any]]

    @property
    def name(self) -> str:
        return self.path.stem


def _load_fixture(path: Path) -> TranscriptFixture:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return TranscriptFixture(
        path=path,
        disclaimer=data["disclaimer"],
        topic_label=data["topic_label"],
        full_text=data["full_text"],
        segments=list(data["segments"]),
        expected_recap=dict(data["expected_recap"]),
        test_queries=list(data.get("test_queries", [])),
    )


def _all_fixtures() -> list[TranscriptFixture]:
    files = sorted(FIXTURES_DIR.glob("transcript_*.json"))
    if not files:
        raise RuntimeError(
            f"No transcript fixtures found in {FIXTURES_DIR}. "
            "Expected transcript_*.json files."
        )
    return [_load_fixture(p) for p in files]


@pytest.fixture(scope="session")
def all_transcript_fixtures() -> list[TranscriptFixture]:
    """All 6 synthetic transcript fixtures."""
    return _all_fixtures()


# ---------------------------------------------------------------------------
# Deterministic pseudo-embedding
# ---------------------------------------------------------------------------


# Topic vocabulary: these tokens get a boosted projection so that semantically
# related chunks cluster. The mapping is fixed so same text -> same vector,
# and similar text (sharing tokens) -> similar vector.
_TOPIC_TOKENS = [
    "anxiety", "anxious", "deadline", "performance", "work", "standup",
    "grief", "loss", "mother", "mom", "bereavement", "belongings", "continuing",
    "sleep", "insomnia", "curfew", "hygiene", "wake", "screen", "stimulus",
    "relationship", "partner", "conflict", "statement", "check-in",
    "alcohol", "drinking", "wine", "drink", "moderation", "motivational",
    "suicidal", "ideation", "crisis", "safety", "isolation", "lifeline",
    "coping", "breathing", "box", "pause", "grounding", "strategy",
    "journal", "journaling", "letter", "homework", "experiment",
]

_SPLIT_RE = re.compile(r"\b[a-zA-Z][a-zA-Z\-']{1,}\b")


def _stable_bucket(token: str) -> int:
    """Map a token to a stable index in [0, EMBEDDING_DIM)."""
    h = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % EMBEDDING_DIM


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _SPLIT_RE.findall(text)]


def fake_embed(text: str) -> list[float]:
    """Produce a deterministic pseudo-embedding for `text`.

    Scheme:
    - Start from an all-zero vector of length EMBEDDING_DIM.
    - For every token in the text, add a small weight at its stable bucket.
    - Topic tokens get a much larger weight so same-topic chunks cluster.
    - Mix in a per-text hash ripple so identical chunks are exactly equal
      but different chunks with no shared tokens aren't artificially similar.
    - L2-normalize so cosine similarity == dot product.

    Same text -> identical vector. Similar text (shared topic tokens) ->
    high cosine similarity.
    """
    vec = [0.0] * EMBEDDING_DIM
    tokens = _tokenize(text)
    if not tokens:
        # Pure hash fallback so even empty/unusual text gets a vector.
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        for i, byte in enumerate(digest):
            vec[i % EMBEDDING_DIM] += (byte / 127.5) - 1.0
        return _normalize(vec)

    topic_set = set(_TOPIC_TOKENS)
    for token in tokens:
        bucket = _stable_bucket(token)
        weight = 6.0 if token in topic_set else 1.0
        vec[bucket] += weight

    # Low-amplitude ripple keyed to the whole text so two chunks that share
    # only the stopword scaffold aren't spuriously similar.
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    for i, byte in enumerate(digest):
        vec[i * 7 % EMBEDDING_DIM] += ((byte / 127.5) - 1.0) * 0.15

    return _normalize(vec)


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (assumed equal length)."""
    return sum(x * y for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------------------
# FakeEmbeddingClient
# ---------------------------------------------------------------------------


@dataclass
class FakeEmbeddingResult:
    """Minimal shape mirroring src.services.embedding_client.EmbeddingResult."""

    text: str
    embedding: list[float]
    model: str = "fake-embedding"
    token_count: int = 0


class FakeEmbeddingClient:
    """Deterministic embedding client for evaluation runs.

    API surface matches the real EmbeddingClient for the methods used by
    the harness.
    """

    EMBEDDING_DIMENSION = EMBEDDING_DIM

    async def embed_text(self, text: str) -> FakeEmbeddingResult:
        return FakeEmbeddingResult(
            text=text,
            embedding=fake_embed(text),
            token_count=max(1, len(text) // 4),
        )

    async def embed_batch(self, texts: list[str]) -> list[FakeEmbeddingResult]:
        return [await self.embed_text(t) for t in texts]

    # Kept for parity with the real client; not exercised in eval but safe.
    async def close(self) -> None:
        return None


@pytest.fixture
def mock_embedding_client() -> FakeEmbeddingClient:
    """Deterministic embedding client that does not call OpenAI."""
    return FakeEmbeddingClient()


# ---------------------------------------------------------------------------
# FakeClaudeClient — canned JSON for recap prompts
# ---------------------------------------------------------------------------


class FakeClaudeError(RuntimeError):
    """Raised when the fake client cannot find a canned response."""


class FakeClaudeClient:
    """Canned-response Claude client.

    Routing:
    - If the user message contains a fixture's disclaimer text, return
      a pre-baked JSON recap matching that fixture's expected_recap.
    - Otherwise raise — unknown inputs should fail loudly rather than
      silently return fake data.
    """

    DEFAULT_MODEL = "fake-claude"

    def __init__(self, fixtures: list[TranscriptFixture]) -> None:
        self._fixtures = fixtures

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> ChatResponse:
        if not messages:
            raise FakeClaudeError("FakeClaudeClient.chat called with no messages")

        user_content = messages[-1].content
        fixture = self._match_fixture(user_content)
        if fixture is None:
            raise FakeClaudeError(
                "FakeClaudeClient could not match input to any fixture. "
                "Ensure the transcript fixture's disclaimer appears in the user message."
            )

        payload = self._build_recap_payload(fixture)
        return ChatResponse(
            content=json.dumps(payload),
            model=self.DEFAULT_MODEL,
            input_tokens=len(user_content) // 4,
            output_tokens=len(json.dumps(payload)) // 4,
            stop_reason="end_turn",
        )

    def _match_fixture(self, user_content: str) -> TranscriptFixture | None:
        # The disclaimer is unique per fixture and is included in the rendered
        # transcript when the fixture is fed to the service under test.
        for fx in self._fixtures:
            if fx.disclaimer in user_content:
                return fx
            # Fall back: match on a distinctive substring of the topic label
            if f"topic:{fx.topic_label}" in user_content:
                return fx
        return None

    @staticmethod
    def _build_recap_payload(fixture: TranscriptFixture) -> dict[str, Any]:
        """Build a plausible recap JSON matching the fixture's expectations.

        The LLM is a fake, so we deterministically return structured content
        that will satisfy the expected_recap assertions. The brief is a real
        synthesis of the fixture's full_text so it passes length checks.
        """
        expected = fixture.expected_recap
        topics = list(expected.get("key_topics_any_of", []))
        tone_pool = list(expected.get("emotional_tone_contains_any", []))
        tone = ", ".join(tone_pool[:2]) if tone_pool else None

        brief = (
            fixture.full_text.strip()
            if 30 <= len(fixture.full_text.strip()) <= 1900
            else fixture.full_text.strip()[:1900]
        )
        if len(brief) < 30:
            brief = (
                f"Session covered {fixture.topic_label} with discussion of "
                f"{', '.join(topics[:3])}. Fictional synthesized transcript."
            )

        risk_flags: list[str] = []
        if expected.get("expected_risk_flags"):
            risk_pool = expected.get("risk_flag_substring_any") or [
                "I've been thinking"
            ]
            # Quote the actual phrase from the transcript if present; else use
            # the expected substring as a paraphrase.
            quote = risk_pool[0]
            for seg in fixture.segments:
                text = seg.get("text", "")
                if any(sub in text for sub in risk_pool):
                    start = seg.get("start_time")
                    timestamp = (
                        f" (~{start:.1f}s)"
                        if isinstance(start, (int, float))
                        else ""
                    )
                    quote = f'"{text.strip()}"{timestamp}'
                    break
            risk_flags = [quote]

        return {
            "brief": brief[:1900],
            "key_topics": topics[:5] if topics else [fixture.topic_label],
            "emotional_tone": tone,
            "homework_assigned": [],
            "follow_ups": [],
            "risk_flags": risk_flags,
        }

    async def close(self) -> None:
        return None


@pytest.fixture
def mock_claude_client(
    all_transcript_fixtures: list[TranscriptFixture],
) -> FakeClaudeClient:
    """Claude client that returns canned JSON for recap prompts."""
    return FakeClaudeClient(fixtures=all_transcript_fixtures)


# ---------------------------------------------------------------------------
# Fake in-memory vector search repo
# ---------------------------------------------------------------------------


@dataclass
class StoredChunk:
    """In-memory mirror of SessionChunk with just the fields search needs."""

    id: uuid.UUID
    session_id: uuid.UUID
    content: str
    embedding: list[float]
    start_time: float | None = None
    end_time: float | None = None
    speaker: str | None = None


@dataclass
class FakeSearchResult:
    chunk: StoredChunk
    score: float


@dataclass
class FakeVectorSearchRepo:
    """In-memory cosine-similarity search over stored chunks, per patient."""

    # Map from patient_id -> list of stored chunks.
    _by_patient: dict[uuid.UUID, list[StoredChunk]] = field(default_factory=dict)

    def add_chunks(
        self,
        patient_id: uuid.UUID,
        chunks: list[StoredChunk],
    ) -> None:
        self._by_patient.setdefault(patient_id, []).extend(chunks)

    async def search_similar(
        self,
        query_embedding: list[float],
        patient_id: uuid.UUID,
        top_k: int = 5,
        min_score: float | None = None,
        session_ids: list[uuid.UUID] | None = None,
    ) -> list[FakeSearchResult]:
        candidates = self._by_patient.get(patient_id, [])
        if session_ids:
            allowed = set(session_ids)
            candidates = [c for c in candidates if c.session_id in allowed]

        scored = [
            FakeSearchResult(chunk=c, score=cosine(query_embedding, c.embedding))
            for c in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)

        if min_score is not None:
            scored = [r for r in scored if r.score >= min_score]

        return scored[:top_k]


@pytest.fixture
def fake_vector_search_repo() -> FakeVectorSearchRepo:
    """Fresh in-memory vector repo per test."""
    return FakeVectorSearchRepo()
