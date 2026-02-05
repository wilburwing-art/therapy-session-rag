"""Tests for RelevanceScorer."""

import pytest

from src.evaluation.relevance_scorer import RelevanceScorer


@pytest.fixture
def scorer() -> RelevanceScorer:
    return RelevanceScorer()


class TestRelevanceScore:
    """Tests for RelevanceScorer.score()."""

    def test_highly_relevant_response(self, scorer: RelevanceScorer) -> None:
        query = "What did we discuss about my anxiety?"
        response = (
            "In your session, you discussed anxiety related to work deadlines. "
            "You explored coping strategies for managing anxiety symptoms."
        )
        result = scorer.score(query, response)
        assert result.score > 0.3
        assert result.query_coverage > 0.3

    def test_irrelevant_response(self, scorer: RelevanceScorer) -> None:
        query = "What did we discuss about my anxiety?"
        response = (
            "The weather today is sunny with clear skies. "
            "The stock market performed well this quarter."
        )
        result = scorer.score(query, response)
        assert result.score < 0.3

    def test_empty_query(self, scorer: RelevanceScorer) -> None:
        result = scorer.score("", "Some response text here")
        assert result.score == 0.0

    def test_empty_response(self, scorer: RelevanceScorer) -> None:
        result = scorer.score("What about my anxiety?", "")
        assert result.score == 0.0

    def test_partial_relevance(self, scorer: RelevanceScorer) -> None:
        query = "Tell me about my sleep patterns and exercise routine"
        response = (
            "Your session notes mention sleep patterns and difficulty falling asleep. "
            "No information about cooking or travel was discussed."
        )
        result = scorer.score(query, response)
        assert 0.0 < result.score < 1.0

    def test_identical_text(self, scorer: RelevanceScorer) -> None:
        text = "Anxiety management through cognitive behavioral therapy techniques"
        result = scorer.score(text, text)
        assert result.score > 0.5
        assert result.query_coverage == 1.0

    def test_score_bounded(self, scorer: RelevanceScorer) -> None:
        result = scorer.score(
            "What about therapy?",
            "Therapy is helpful for managing mental health."
        )
        assert 0.0 <= result.score <= 1.0
        assert 0.0 <= result.query_coverage <= 1.0
        assert 0.0 <= result.response_focus <= 1.0
