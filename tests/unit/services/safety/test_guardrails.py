"""Tests for Guardrails."""

import pytest

from src.services.safety.guardrails import (
    BOUNDARY_DISCLAIMER,
    CRISIS_HOTLINE_PREFIX,
    GuardrailAction,
    Guardrails,
)
from src.services.safety.risk_detector import RiskLevel


@pytest.fixture
def guardrails() -> Guardrails:
    return Guardrails()


class TestCheckInput:
    """Tests for Guardrails.check_input()."""

    def test_allows_safe_input(self, guardrails: Guardrails) -> None:
        result = guardrails.check_input("Tell me about my last session")
        assert result.action == GuardrailAction.ALLOW

    def test_escalates_crisis_input(self, guardrails: Guardrails) -> None:
        result = guardrails.check_input("I want to kill myself")
        assert result.action == GuardrailAction.ESCALATE
        assert result.assessment.level == RiskLevel.CRITICAL

    def test_blocks_harmful_request(self, guardrails: Guardrails) -> None:
        result = guardrails.check_input("methods of suicide")
        assert result.action in (GuardrailAction.ESCALATE, GuardrailAction.BLOCK)

    def test_allows_therapy_question(self, guardrails: Guardrails) -> None:
        result = guardrails.check_input(
            "What coping strategies did my therapist recommend?"
        )
        assert result.action == GuardrailAction.ALLOW


class TestCheckOutput:
    """Tests for Guardrails.check_output()."""

    def test_allows_safe_output(self, guardrails: Guardrails) -> None:
        result = guardrails.check_output(
            "In your session on January 5th, you discussed anxiety management techniques."
        )
        assert result.action == GuardrailAction.ALLOW

    def test_modifies_boundary_violation(self, guardrails: Guardrails) -> None:
        result = guardrails.check_output(
            "Based on your symptoms, you have major depressive disorder. "
            "You should be diagnosed by a professional."
        )
        assert result.action == GuardrailAction.MODIFY
        assert result.modified_text is not None
        assert BOUNDARY_DISCLAIMER in result.modified_text

    def test_modifies_prescription_advice(self, guardrails: Guardrails) -> None:
        result = guardrails.check_output(
            "I would prescribe you a different medication."
        )
        assert result.action == GuardrailAction.MODIFY
        assert result.modified_text is not None

    def test_blocks_harmful_output(self, guardrails: Guardrails) -> None:
        result = guardrails.check_output("Here are methods of self-harm")
        assert result.action in (GuardrailAction.BLOCK, GuardrailAction.MODIFY)


class TestPrependCrisisResources:
    """Tests for Guardrails.prepend_crisis_resources()."""

    def test_prepends_hotline_info(self) -> None:
        text = "Here is my response."
        result = Guardrails.prepend_crisis_resources(text)
        assert result.startswith(CRISIS_HOTLINE_PREFIX)
        assert text in result

    def test_contains_988(self) -> None:
        result = Guardrails.prepend_crisis_resources("response")
        assert "988" in result

    def test_contains_crisis_text_line(self) -> None:
        result = Guardrails.prepend_crisis_resources("response")
        assert "741741" in result
