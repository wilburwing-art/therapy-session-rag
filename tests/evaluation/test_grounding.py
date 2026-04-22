"""Unit tests for the lexical grounding metric."""

from __future__ import annotations

import uuid

import pytest

from src.evaluation.grounding import compute_grounding_score
from src.models.domain.chat import ChatSource

pytestmark = pytest.mark.evaluation


def _source(text: str, score: float = 0.9) -> ChatSource:
    return ChatSource(
        session_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        content_preview=text[:200],
        relevance_score=score,
        start_time=None,
        speaker=None,
    )


def test_perfectly_grounded_answer_scores_1() -> None:
    sources = [_source("We discussed box breathing and the three-minute pause for work anxiety.")]
    answer = "You practiced box breathing. You also tried the three-minute pause for anxiety."
    assert compute_grounding_score(answer, sources) == 1.0


def test_random_unrelated_text_scores_low() -> None:
    sources = [_source("Session covered grief, loss, and continuing bonds with a mother who recently died.")]
    answer = (
        "Quantum chromodynamics predicts asymptotic freedom. "
        "Kubernetes scheduling relies on taints and tolerations. "
        "Sourdough fermentation depends on wild yeast populations."
    )
    score = compute_grounding_score(answer, sources)
    assert score < 0.3, f"expected <0.3, got {score}"


def test_empty_answer_returns_1() -> None:
    sources = [_source("Session covered sleep hygiene and CBT-I stimulus control.")]
    assert compute_grounding_score("", sources) == 1.0
    assert compute_grounding_score("   ", sources) == 1.0


def test_answer_with_no_sources_mostly_ungrounded() -> None:
    # No sources means any sentence with meaningful tokens is ungrounded.
    answer = "You talked about anxiety. You practiced breathing."
    score = compute_grounding_score(answer, sources=[])
    assert score < 0.5, f"expected <0.5, got {score}"


def test_answer_with_no_sources_and_no_tokens_is_grounded() -> None:
    # Pure filler sentences (stopwords only) count as grounded with no sources.
    score = compute_grounding_score("Yes. The. And you.", sources=[])
    # Every sentence tokenizes to empty or near-empty after stopword removal.
    assert score >= 0.5


def test_partial_grounding() -> None:
    sources = [_source("Patient discussed anxiety and work deadlines with their therapist.")]
    answer = (
        "You discussed anxiety related to work deadlines. "
        "The stock market closed higher on Friday after the jobs report."
    )
    score = compute_grounding_score(answer, sources)
    # First sentence grounded, second not -> ~0.5
    assert 0.3 <= score <= 0.7, f"expected ~0.5, got {score}"


def test_punctuation_only_answer_returns_1() -> None:
    sources = [_source("anything")]
    assert compute_grounding_score("!!! ??? ...", sources) == 1.0


def test_sources_union_is_taken() -> None:
    # Distributing source tokens across multiple ChatSource objects
    # should be equivalent to one source containing all tokens.
    sources = [
        _source("Box breathing was practiced."),
        _source("Three-minute pause before standups."),
    ]
    answer = "You practiced box breathing and used the three-minute pause before standups."
    assert compute_grounding_score(answer, sources) == 1.0


def test_case_insensitive() -> None:
    sources = [_source("SLEEP HYGIENE and CBT-I STIMULUS control.")]
    answer = "We talked about sleep hygiene and stimulus control."
    assert compute_grounding_score(answer, sources) == 1.0


def test_short_sentence_not_penalized() -> None:
    # A short valid claim like "You practiced box breathing." should count
    # as grounded, not fail due to Jaccard denominator dominance.
    sources = [_source("Box breathing and the three-minute pause were introduced.")]
    answer = "You practiced box breathing."
    assert compute_grounding_score(answer, sources) == 1.0


def test_score_in_unit_interval() -> None:
    sources = [_source("Patient discussed grief after the loss of their mother.")]
    answer = (
        "You discussed grief after your mother's death. "
        "The apartment sorting remains pending. "
        "Something entirely unrelated about cryptography."
    )
    score = compute_grounding_score(answer, sources)
    assert 0.0 <= score <= 1.0
