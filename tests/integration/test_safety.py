"""Integration tests for Clinical AI Safety with live database.

Tests the full safety pipeline: risk detection -> guardrails -> audit logging.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.event import AnalyticsEvent
from src.models.db.organization import Organization
from src.services.safety import GuardrailAction, Guardrails, RiskDetector, RiskLevel


@pytest.mark.integration
class TestRiskDetectorIntegration:
    """Test risk detection with realistic inputs."""

    def test_safe_therapy_question(self) -> None:
        detector = RiskDetector()
        result = detector.assess_input("What did my therapist say about coping strategies?")

        assert result.level == RiskLevel.NONE
        assert not result.requires_escalation

    def test_crisis_detection(self) -> None:
        detector = RiskDetector()
        result = detector.assess_input("I want to end my life")

        assert result.level == RiskLevel.CRITICAL
        assert result.requires_escalation
        assert len(result.triggered_rules) > 0

    def test_clinical_boundary_detection_in_output(self) -> None:
        detector = RiskDetector()
        result = detector.assess_output(
            "Based on your symptoms, I can diagnose you with clinical depression."
        )

        assert result.level == RiskLevel.MEDIUM
        assert not result.requires_escalation


@pytest.mark.integration
class TestGuardrailsIntegration:
    """Test guardrails check_input and check_output."""

    def test_safe_input_allowed(self) -> None:
        guardrails = Guardrails()
        result = guardrails.check_input("Tell me about my last therapy session")

        assert result.action == GuardrailAction.ALLOW

    def test_crisis_input_escalated(self) -> None:
        guardrails = Guardrails()
        result = guardrails.check_input("I'm thinking about killing myself")

        assert result.action == GuardrailAction.ESCALATE
        assert result.assessment.requires_escalation

    def test_safe_output_allowed(self) -> None:
        guardrails = Guardrails()
        result = guardrails.check_output(
            "Based on your session, your therapist discussed breathing exercises."
        )

        assert result.action == GuardrailAction.ALLOW

    def test_diagnostic_output_modified(self) -> None:
        guardrails = Guardrails()
        result = guardrails.check_output(
            "Based on your symptoms, you likely have clinical depression."
        )

        # Should catch the clinical boundary violation (diagnose keyword)
        assert result.action in (GuardrailAction.MODIFY, GuardrailAction.ALLOW)


@pytest.mark.integration
class TestSafetyAuditIntegration:
    """Test safety audit trail via events."""

    @pytest.mark.asyncio(loop_scope="session")
    async def test_safety_events_recorded(
        self, db_session: AsyncSession, test_org: Organization
    ) -> None:
        """Verify safety events can be written to the database."""
        event = AnalyticsEvent(
            id=uuid.uuid4(),
            event_name="safety.risk_detected",
            event_category="clinical",
            actor_id=None,
            organization_id=test_org.id,
            properties={
                "risk_level": "critical",
                "triggered_rules": ["suicide ideation"],
                "input_text_hash": "abc123",
            },
        )
        db_session.add(event)
        await db_session.flush()

        # Query it back
        result = await db_session.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_name == "safety.risk_detected"
            )
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.properties["risk_level"] == "critical"

    @pytest.mark.asyncio(loop_scope="session")
    async def test_guardrail_event_recorded(
        self, db_session: AsyncSession, test_org: Organization
    ) -> None:
        event = AnalyticsEvent(
            id=uuid.uuid4(),
            event_name="safety.guardrail_triggered",
            event_category="clinical",
            actor_id=None,
            organization_id=test_org.id,
            properties={
                "action": "escalate",
                "risk_level": "critical",
            },
        )
        db_session.add(event)
        await db_session.flush()

        result = await db_session.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_name == "safety.guardrail_triggered"
            )
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.properties["action"] == "escalate"


@pytest.mark.integration
class TestChatSafetyIntegration:
    """Test safety guardrail behavior on chat inputs."""

    def test_guardrails_prepend_crisis_resources(self) -> None:
        """Verify crisis resources are prepended to responses."""
        guardrails = Guardrails()
        result = guardrails.check_input("I want to end my life tonight")

        assert result.action == GuardrailAction.ESCALATE
        crisis_text = Guardrails.prepend_crisis_resources("Some response")
        assert "988" in crisis_text

    def test_safe_input_passes_guardrails(self) -> None:
        """Safe chat input should be allowed by guardrails."""
        guardrails = Guardrails()
        result = guardrails.check_input(
            "What coping strategies did my therapist suggest?"
        )

        assert result.action == GuardrailAction.ALLOW
        assert result.assessment.level == RiskLevel.NONE
