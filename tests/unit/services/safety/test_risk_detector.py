"""Tests for RiskDetector."""

import pytest

from src.services.safety.risk_detector import RiskDetector, RiskLevel


@pytest.fixture
def detector() -> RiskDetector:
    return RiskDetector()


class TestAssessInput:
    """Tests for RiskDetector.assess_input()."""

    def test_safe_input(self, detector: RiskDetector) -> None:
        result = detector.assess_input("What did we discuss last session?")
        assert result.level == RiskLevel.NONE
        assert result.triggered_rules == []
        assert not result.requires_escalation

    def test_detects_suicide_mention(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I've been having thoughts of suicide")
        assert result.level == RiskLevel.CRITICAL
        assert "crisis_suicide" in result.triggered_rules
        assert result.requires_escalation
        assert result.recommended_action == "escalate"

    def test_detects_self_harm(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I've been self-harming again")
        assert result.level == RiskLevel.CRITICAL
        assert any("self_harm" in r for r in result.triggered_rules)

    def test_detects_want_to_die(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I just want to die")
        assert result.level == RiskLevel.CRITICAL
        assert result.requires_escalation

    def test_detects_end_it_all(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I want to end it all")
        assert result.level == RiskLevel.CRITICAL

    def test_detects_overdose(self, detector: RiskDetector) -> None:
        result = detector.assess_input("thinking about overdosing")
        assert result.level == RiskLevel.CRITICAL

    def test_detects_harm_others(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I feel like killing someone")
        assert result.level == RiskLevel.CRITICAL
        assert any("harm_others" in r for r in result.triggered_rules)

    def test_detects_harmful_request(self, detector: RiskDetector) -> None:
        result = detector.assess_input("how to kill yourself")
        # Matches both crisis (suicide) and harmful patterns
        assert result.level in (RiskLevel.CRITICAL, RiskLevel.HIGH)

    def test_case_insensitive(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I AM SUICIDAL")
        assert result.level == RiskLevel.CRITICAL

    def test_therapy_discussion_not_flagged(self, detector: RiskDetector) -> None:
        result = detector.assess_input("We discussed my anxiety and sleep patterns")
        assert result.level == RiskLevel.NONE

    def test_multiple_triggers(self, detector: RiskDetector) -> None:
        result = detector.assess_input("I'm suicidal and want to end everything")
        assert result.level == RiskLevel.CRITICAL
        assert len(result.triggered_rules) >= 2


class TestAssessOutput:
    """Tests for RiskDetector.assess_output()."""

    def test_safe_output(self, detector: RiskDetector) -> None:
        result = detector.assess_output(
            "Based on your session notes, you discussed coping strategies for anxiety."
        )
        assert result.level == RiskLevel.NONE

    def test_detects_diagnosis(self, detector: RiskDetector) -> None:
        result = detector.assess_output("You have been diagnosed with depression")
        assert result.level == RiskLevel.MEDIUM
        assert any("diagnosis" in r for r in result.triggered_rules)
        assert result.recommended_action == "modify"

    def test_detects_prescription(self, detector: RiskDetector) -> None:
        result = detector.assess_output("I would prescribe a different medication")
        assert result.level == RiskLevel.MEDIUM
        assert any("prescription" in r for r in result.triggered_rules)

    def test_detects_undermine_provider(self, detector: RiskDetector) -> None:
        result = detector.assess_output("You should stop seeing your therapist")
        assert result.level == RiskLevel.MEDIUM
        assert any("undermine_provider" in r for r in result.triggered_rules)

    def test_general_medical_mention_ok(self, detector: RiskDetector) -> None:
        result = detector.assess_output(
            "Your therapist can help you explore these feelings further."
        )
        assert result.level == RiskLevel.NONE

    def test_detects_harmful_output(self, detector: RiskDetector) -> None:
        result = detector.assess_output("methods of self-harm include")
        assert result.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
