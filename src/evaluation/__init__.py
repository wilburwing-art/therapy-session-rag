"""LLM evaluation framework for RAG quality and clinical safety."""

from src.evaluation.clinical_accuracy import ClinicalAccuracyChecker
from src.evaluation.eval_suite import EvalCase, EvalResult, EvalSuite
from src.evaluation.hallucination_detector import HallucinationDetector
from src.evaluation.relevance_scorer import RelevanceScorer

__all__ = [
    "ClinicalAccuracyChecker",
    "EvalCase",
    "EvalResult",
    "EvalSuite",
    "HallucinationDetector",
    "RelevanceScorer",
]
