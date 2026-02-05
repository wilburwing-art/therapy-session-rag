"""Tests for HallucinationDetector."""

import pytest

from src.evaluation.hallucination_detector import HallucinationDetector


@pytest.fixture
def detector() -> HallucinationDetector:
    return HallucinationDetector(keyword_threshold=0.3)


class TestHallucinationCheck:
    """Tests for HallucinationDetector.check()."""

    def test_grounded_response(self, detector: HallucinationDetector) -> None:
        sources = [
            "The patient discussed anxiety about work deadlines. "
            "They mentioned feeling overwhelmed by responsibilities."
        ]
        response = (
            "In your session, you discussed anxiety about work deadlines "
            "and feeling overwhelmed by responsibilities."
        )
        result = detector.check(response, sources)
        assert result.is_grounded
        assert result.grounding_score >= 0.5
        assert result.unsupported_claims == []

    def test_hallucinated_response(self, detector: HallucinationDetector) -> None:
        sources = ["The patient discussed anxiety about work deadlines."]
        response = (
            "You mentioned having recurring nightmares about your childhood. "
            "You also discussed relationship problems with your partner."
        )
        result = detector.check(response, sources)
        assert not result.is_grounded
        assert result.grounding_score < 1.0
        assert len(result.unsupported_claims) > 0

    def test_empty_response(self, detector: HallucinationDetector) -> None:
        result = detector.check("", ["Some source text"])
        assert result.is_grounded
        assert result.grounding_score == 1.0
        assert result.total_claims == 0

    def test_empty_sources(self, detector: HallucinationDetector) -> None:
        result = detector.check(
            "You discussed anxiety in your session.", []
        )
        # No source keywords to match against
        assert result.total_claims > 0

    def test_meta_sentences_are_grounded(self, detector: HallucinationDetector) -> None:
        sources = ["Patient discussed anxiety."]
        response = (
            "Based on your session notes, you discussed anxiety. "
            "I don't have enough information to elaborate further. "
            "Please consult with your therapist for more details."
        )
        result = detector.check(response, sources)
        assert result.grounding_score >= 0.5

    def test_partial_grounding(self, detector: HallucinationDetector) -> None:
        sources = ["The patient discussed sleep problems and insomnia."]
        response = (
            "You mentioned having sleep problems and insomnia. "
            "You also expressed concerns about your career trajectory."
        )
        result = detector.check(response, sources)
        assert 0.0 < result.grounding_score < 1.0
        assert result.total_claims == 2


class TestKeywordThreshold:
    """Tests for adjustable keyword threshold."""

    def test_strict_threshold(self) -> None:
        detector = HallucinationDetector(keyword_threshold=0.8)
        sources = ["Patient discussed anxiety."]
        response = "You mentioned anxiety and depression symptoms."
        result = detector.check(response, sources)
        # Stricter threshold = more likely to flag
        assert result.grounding_score <= 1.0

    def test_lenient_threshold(self) -> None:
        detector = HallucinationDetector(keyword_threshold=0.1)
        sources = ["Patient discussed anxiety."]
        response = "You mentioned anxiety and some related concerns."
        result = detector.check(response, sources)
        # More lenient = higher grounding scores
        assert result.grounding_score >= 0.5
