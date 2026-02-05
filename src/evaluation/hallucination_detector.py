"""Hallucination detection for RAG responses.

Checks whether claims in an AI response are supported by the provided source text.
Uses string overlap and keyword matching (no external API calls).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class HallucinationResult:
    """Result of hallucination detection."""

    is_grounded: bool
    grounding_score: float  # 0.0 = fully hallucinated, 1.0 = fully grounded
    unsupported_claims: list[str]
    total_claims: int


def _extract_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text (lowercase, 3+ chars)."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    # Filter common stopwords
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


class HallucinationDetector:
    """Detects hallucinated content in AI responses.

    Compares response sentences against source text to identify claims
    not supported by the provided context.
    """

    def __init__(self, keyword_threshold: float = 0.3) -> None:
        """Initialize with keyword overlap threshold.

        Args:
            keyword_threshold: Minimum fraction of response sentence keywords
                that must appear in source text for the sentence to be
                considered grounded. Default 0.3 (30%).
        """
        self.keyword_threshold = keyword_threshold

    def check(self, response: str, source_texts: list[str]) -> HallucinationResult:
        """Check if response is grounded in source texts.

        Args:
            response: The AI-generated response
            source_texts: List of source text chunks the response should be based on

        Returns:
            HallucinationResult with grounding assessment
        """
        response_sentences = _extract_sentences(response)

        if not response_sentences:
            return HallucinationResult(
                is_grounded=True, grounding_score=1.0,
                unsupported_claims=[], total_claims=0,
            )

        # Build combined source keyword set
        combined_source = " ".join(source_texts)
        source_keywords = _extract_keywords(combined_source)

        unsupported: list[str] = []
        grounded_count = 0

        for sentence in response_sentences:
            # Skip meta-sentences (disclaimers, etc.)
            if self._is_meta_sentence(sentence):
                grounded_count += 1
                continue

            sentence_keywords = _extract_keywords(sentence)
            if not sentence_keywords:
                grounded_count += 1
                continue

            overlap = sentence_keywords & source_keywords
            overlap_ratio = len(overlap) / len(sentence_keywords)

            if overlap_ratio >= self.keyword_threshold:
                grounded_count += 1
            else:
                unsupported.append(sentence)

        total = len(response_sentences)
        score = grounded_count / total if total > 0 else 1.0

        return HallucinationResult(
            is_grounded=len(unsupported) == 0,
            grounding_score=round(score, 3),
            unsupported_claims=unsupported,
            total_claims=total,
        )

    @staticmethod
    def _is_meta_sentence(sentence: str) -> bool:
        """Check if sentence is a meta/disclaimer statement."""
        meta_patterns = [
            r"based on (?:your|the) (?:session|therapy)",
            r"(?:i )?don'?t have (?:enough|relevant|specific)",
            r"please (?:consult|speak|talk) (?:with|to) your",
            r"i'?m (?:an )?(?:ai|artificial|assistant)",
            r"(?:note|disclaimer|important):",
        ]
        lower = sentence.lower()
        return any(re.search(p, lower) for p in meta_patterns)
