"""Safety guardrails for clinical AI chat.

Wraps risk detection with actionable responses: ALLOW, MODIFY, BLOCK, ESCALATE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.services.safety.risk_detector import RiskAssessment, RiskDetector, RiskLevel


class GuardrailAction(StrEnum):
    """Action to take based on guardrail check."""

    ALLOW = "allow"
    MODIFY = "modify"
    BLOCK = "block"
    ESCALATE = "escalate"


CRISIS_HOTLINE_PREFIX = (
    "**If you or someone you know is in crisis, please reach out for help:**\n"
    "- **988 Suicide & Crisis Lifeline**: Call or text **988** (US)\n"
    "- **Crisis Text Line**: Text **HOME** to **741741**\n"
    "- **Emergency**: Call **911**\n\n"
    "---\n\n"
)

BOUNDARY_DISCLAIMER = (
    "\n\n---\n"
    "*Note: This AI assistant cannot provide medical diagnoses, prescriptions, "
    "or clinical advice. Please consult your therapist or healthcare provider "
    "for professional guidance.*"
)


@dataclass
class GuardrailResult:
    """Result of a guardrail check."""

    action: GuardrailAction
    assessment: RiskAssessment
    modified_text: str | None = None


class Guardrails:
    """Safety guardrails for clinical AI chat.

    Checks user input and AI output for safety risks. Returns actionable
    results that the chat service uses to decide how to proceed.
    """

    def __init__(self) -> None:
        self._detector = RiskDetector()

    def check_input(self, text: str) -> GuardrailResult:
        """Check user input for safety risks.

        Returns:
            GuardrailResult with appropriate action:
            - ALLOW: Input is safe, proceed normally
            - ESCALATE: Crisis detected, proceed but prepend crisis resources
            - BLOCK: Harmful content request, refuse to process
        """
        assessment = self._detector.assess_input(text)

        if assessment.level == RiskLevel.NONE:
            return GuardrailResult(action=GuardrailAction.ALLOW, assessment=assessment)

        if assessment.level == RiskLevel.CRITICAL:
            return GuardrailResult(
                action=GuardrailAction.ESCALATE,
                assessment=assessment,
            )

        if assessment.level == RiskLevel.HIGH:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                assessment=assessment,
            )

        # LOW/MEDIUM inputs are allowed through
        return GuardrailResult(action=GuardrailAction.ALLOW, assessment=assessment)

    def check_output(self, text: str) -> GuardrailResult:
        """Check AI output for safety risks.

        Returns:
            GuardrailResult with appropriate action:
            - ALLOW: Output is safe
            - MODIFY: Output contains boundary violations, append disclaimer
            - BLOCK: Output contains harmful content
        """
        assessment = self._detector.assess_output(text)

        if assessment.level == RiskLevel.NONE:
            return GuardrailResult(action=GuardrailAction.ALLOW, assessment=assessment)

        if assessment.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                assessment=assessment,
            )

        if assessment.level == RiskLevel.MEDIUM:
            return GuardrailResult(
                action=GuardrailAction.MODIFY,
                assessment=assessment,
                modified_text=text + BOUNDARY_DISCLAIMER,
            )

        return GuardrailResult(action=GuardrailAction.ALLOW, assessment=assessment)

    @staticmethod
    def prepend_crisis_resources(text: str) -> str:
        """Prepend crisis hotline information to a response."""
        return CRISIS_HOTLINE_PREFIX + text
