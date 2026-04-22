"""Lexical grounding metric for RAG answers.

Measures whether sentences in an answer are supported by the retrieved
source chunks, using Jaccard overlap of non-stopword tokens. Hermetic —
no LLM calls, no network.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.models.domain.chat import ChatSource

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "was", "were", "has", "have", "had",
        "been", "will", "would", "could", "should", "can", "may", "might",
        "this", "that", "these", "those", "with", "from", "about", "into",
        "your", "you", "they", "them", "their", "what", "when", "where",
        "how", "who", "which", "also", "very", "just", "than", "then",
        "some", "more", "most", "such", "each", "other", "over", "only",
        "said", "like", "not", "but", "does", "did", "yes", "yeah", "okay",
        "its", "our", "out", "any", "all", "one", "two", "three",
    }
)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"\b[a-zA-Z][a-zA-Z\-']{1,}\b")

_GROUNDING_THRESHOLD = 0.2


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens minus stopwords, length 3+."""
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, stripping whitespace and empties."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _source_tokens(sources: Iterable[ChatSource]) -> set[str]:
    """Union of tokens across all source content previews."""
    tokens: set[str] = set()
    for source in sources:
        tokens |= _tokenize(source.content_preview)
    return tokens


def compute_grounding_score(
    answer_text: str,
    sources: list[ChatSource],
) -> float:
    """Fraction of answer sentences grounded in source content.

    For each sentence:
    - Extract meaningful tokens (non-stopword, length 3+).
    - Compute Jaccard overlap against the union of source tokens.
    - Sentence is grounded if overlap > _GROUNDING_THRESHOLD (0.2).

    Sentences with no meaningful tokens (pure filler) are counted as grounded
    since they make no claims to ungroud.

    Args:
        answer_text: The generated answer text.
        sources: The retrieved source chunks used to generate the answer.

    Returns:
        Fraction in [0.0, 1.0]. Empty answer returns 1.0 (no claims).
    """
    sentences = _split_sentences(answer_text)
    if not sentences:
        return 1.0

    source_toks = _source_tokens(sources)
    if not source_toks:
        # No sources — any non-trivial claim is ungrounded.
        # Sentences with no tokens still count as grounded (no claim).
        grounded = 0
        for sentence in sentences:
            if not _tokenize(sentence):
                grounded += 1
        return grounded / len(sentences)

    grounded = 0
    for sentence in sentences:
        sent_toks = _tokenize(sentence)
        if not sent_toks:
            grounded += 1
            continue
        overlap = sent_toks & source_toks
        union = sent_toks | source_toks
        if not union:
            grounded += 1
            continue
        jaccard = len(overlap) / len(union)
        # Fall back to sentence-local overlap ratio for short sentences where
        # the union is dominated by source tokens and Jaccard is structurally
        # tiny. Use the larger of the two.
        sent_ratio = len(overlap) / len(sent_toks)
        score = max(jaccard, sent_ratio)
        if score > _GROUNDING_THRESHOLD:
            grounded += 1

    return grounded / len(sentences)
