"""Risk detection for clinical AI safety.

Detects crisis signals, harmful content, and clinical boundary violations
in both user inputs and AI outputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class RiskLevel(StrEnum):
    """Risk severity levels."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskAssessment:
    """Result of a risk detection analysis."""

    level: RiskLevel
    triggered_rules: list[str] = field(default_factory=list)
    requires_escalation: bool = False
    recommended_action: str = "allow"


# Crisis keywords indicating immediate danger
_CRISIS_PATTERNS: list[tuple[str, str]] = [
    (r"\b(suicid(?:e|al|ality))\b", "crisis_suicide"),
    (r"\b(kill(?:ing)?\s+(?:my)?self)\b", "crisis_self_harm"),
    (r"\b(want(?:ing)?\s+to\s+die)\b", "crisis_want_to_die"),
    (r"\b(end(?:ing)?\s+(?:my|it\s+all|everything))\b", "crisis_end_it"),
    (r"\b(self[- ]?harm(?:ing)?)\b", "crisis_self_harm"),
    (r"\b(cut(?:ting)?\s+(?:my)?self)\b", "crisis_self_harm_cutting"),
    (r"\b(overdos(?:e|ing))\b", "crisis_overdose"),
    (r"\b(homicid(?:e|al))\b", "crisis_homicide"),
    (r"\b(kill(?:ing)?\s+(?:some(?:one|body)|them|him|her))\b", "crisis_harm_others"),
    (r"\b(plan(?:ning)?\s+to\s+(?:hurt|harm|kill))\b", "crisis_plan"),
]

# Patterns that suggest clinical boundary violations in AI output
_CLINICAL_BOUNDARY_PATTERNS: list[tuple[str, str]] = [
    (r"\b(diagnos(?:e|is|ed|ing))\b", "boundary_diagnosis"),
    (r"\b(prescrib(?:e|ing|ed))\b", "boundary_prescription"),
    (r"\b(you\s+(?:have|suffer\s+from|are\s+(?:diagnosed|suffering)))\b", "boundary_diagnosis_statement"),
    (r"\b(you\s+should\s+(?:take|stop\s+taking)\s+(?:your\s+)?(?:medic(?:ation|ine)))\b", "boundary_medication_advice"),
    (r"\b(stop\s+(?:seeing|going\s+to)\s+(?:your\s+)?(?:therapist|doctor))\b", "boundary_undermine_provider"),
]

# Harmful content patterns
_HARMFUL_CONTENT_PATTERNS: list[tuple[str, str]] = [
    (r"\b(how\s+to\s+(?:kill|hurt|harm)\s+(?:your)?self)\b", "harmful_instructions"),
    (r"\b(methods?\s+(?:of|for)\s+(?:suicide|self[- ]?harm))\b", "harmful_methods"),
    (r"\b(ways\s+to\s+(?:kill|hurt|harm)\s+(?:your)?self)\b", "harmful_ways"),
]

_COMPILED_CRISIS = [(re.compile(p, re.IGNORECASE), name) for p, name in _CRISIS_PATTERNS]
_COMPILED_BOUNDARY = [(re.compile(p, re.IGNORECASE), name) for p, name in _CLINICAL_BOUNDARY_PATTERNS]
_COMPILED_HARMFUL = [(re.compile(p, re.IGNORECASE), name) for p, name in _HARMFUL_CONTENT_PATTERNS]


class RiskDetector:
    """Detects risk signals in text content.

    Applies pattern-based rules to identify crisis signals, clinical boundary
    violations, and harmful content.
    """

    def assess_input(self, text: str) -> RiskAssessment:
        """Assess risk level of user input.

        Checks for crisis signals and harmful content requests.
        """
        triggered: list[str] = []

        # Check crisis patterns
        for pattern, rule_name in _COMPILED_CRISIS:
            if pattern.search(text):
                triggered.append(rule_name)

        # Check harmful content requests
        for pattern, rule_name in _COMPILED_HARMFUL:
            if pattern.search(text):
                triggered.append(rule_name)

        return self._build_assessment(triggered)

    def assess_output(self, text: str) -> RiskAssessment:
        """Assess risk level of AI-generated output.

        Checks for clinical boundary violations and harmful content.
        """
        triggered: list[str] = []

        # Check clinical boundary violations
        for pattern, rule_name in _COMPILED_BOUNDARY:
            if pattern.search(text):
                triggered.append(rule_name)

        # Check harmful content in output
        for pattern, rule_name in _COMPILED_HARMFUL:
            if pattern.search(text):
                triggered.append(rule_name)

        return self._build_assessment(triggered)

    def _build_assessment(self, triggered: list[str]) -> RiskAssessment:
        """Build a RiskAssessment from triggered rules."""
        if not triggered:
            return RiskAssessment(level=RiskLevel.NONE)

        # Any crisis pattern → CRITICAL
        crisis_rules = [r for r in triggered if r.startswith("crisis_")]
        if crisis_rules:
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                triggered_rules=triggered,
                requires_escalation=True,
                recommended_action="escalate",
            )

        # Harmful content → HIGH
        harmful_rules = [r for r in triggered if r.startswith("harmful_")]
        if harmful_rules:
            return RiskAssessment(
                level=RiskLevel.HIGH,
                triggered_rules=triggered,
                requires_escalation=False,
                recommended_action="block",
            )

        # Boundary violations → MEDIUM
        boundary_rules = [r for r in triggered if r.startswith("boundary_")]
        if boundary_rules:
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                triggered_rules=triggered,
                requires_escalation=False,
                recommended_action="modify",
            )

        return RiskAssessment(
            level=RiskLevel.LOW,
            triggered_rules=triggered,
        )
