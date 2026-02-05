"""Relevance scoring for RAG query-response pairs.

Measures how relevant an AI response is to the user's query using
keyword overlap (no external API calls needed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RelevanceResult:
    """Result of relevance scoring."""

    score: float  # 0.0 = irrelevant, 1.0 = highly relevant
    query_coverage: float  # Fraction of query keywords present in response
    response_focus: float  # Fraction of response keywords related to query


def _extract_meaningful_words(text: str) -> set[str]:
    """Extract meaningful words (lowercase, 3+ chars, no stopwords)."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    stopwords = {
        "the", "and", "for", "are", "was", "were", "has", "have", "had",
        "been", "will", "would", "could", "should", "can", "may", "might",
        "this", "that", "these", "those", "with", "from", "about", "into",
        "your", "you", "they", "them", "their", "what", "when", "where",
        "how", "who", "which", "also", "very", "just", "than", "then",
        "some", "more", "most", "such", "each", "other", "over", "only",
        "said", "like", "not", "but", "does", "did",
    }
    return {w for w in words if w not in stopwords}


class RelevanceScorer:
    """Scores the relevance of a response to a query.

    Uses bidirectional keyword overlap: how much of the query is
    addressed in the response, and how focused the response is
    on the query topic.
    """

    def score(self, query: str, response: str) -> RelevanceResult:
        """Score the relevance of a response to a query.

        Args:
            query: The user's original query
            response: The AI-generated response

        Returns:
            RelevanceResult with score breakdown
        """
        query_words = _extract_meaningful_words(query)
        response_words = _extract_meaningful_words(response)

        if not query_words or not response_words:
            return RelevanceResult(score=0.0, query_coverage=0.0, response_focus=0.0)

        # How much of the query is covered in the response
        query_in_response = query_words & response_words
        query_coverage = len(query_in_response) / len(query_words)

        # How focused the response is on query topics
        response_on_query = query_words & response_words
        response_focus = len(response_on_query) / len(response_words)

        # Combined score (weighted toward query coverage)
        combined = query_coverage * 0.7 + response_focus * 0.3

        return RelevanceResult(
            score=round(combined, 3),
            query_coverage=round(query_coverage, 3),
            response_focus=round(response_focus, 3),
        )
