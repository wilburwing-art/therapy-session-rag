"""Safety audit logging via the EventPublisher.

Publishes safety events for compliance tracking and analytics:
- safety.risk_detected
- safety.guardrail_triggered
- safety.escalation_created
"""

from __future__ import annotations

import uuid
from typing import Any

from src.models.db.event import EventCategory
from src.services.event_service import EventPublisher
from src.services.safety.guardrails import GuardrailAction, GuardrailResult
from src.services.safety.risk_detector import RiskAssessment


class SafetyAuditor:
    """Publishes safety events to the analytics event stream."""

    def __init__(self, event_publisher: EventPublisher) -> None:
        self._publisher = event_publisher

    async def log_risk_assessment(
        self,
        assessment: RiskAssessment,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        session_id: uuid.UUID | None = None,
        context: str = "input",
    ) -> None:
        """Log a risk detection event."""
        if not assessment.triggered_rules:
            return  # Nothing to log for clean assessments

        properties: dict[str, Any] = {
            "risk_level": assessment.level.value,
            "triggered_rules": assessment.triggered_rules,
            "requires_escalation": assessment.requires_escalation,
            "recommended_action": assessment.recommended_action,
            "context": context,
        }

        await self._publisher.publish(
            event_name="safety.risk_detected",
            category=EventCategory.CLINICAL,
            organization_id=organization_id,
            actor_id=actor_id,
            session_id=session_id,
            properties=properties,
        )

    async def log_guardrail_action(
        self,
        result: GuardrailResult,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        context: str = "input",
    ) -> None:
        """Log a guardrail trigger event."""
        if result.action == GuardrailAction.ALLOW:
            return  # Don't log allows to reduce noise

        await self._publisher.publish(
            event_name="safety.guardrail_triggered",
            category=EventCategory.CLINICAL,
            organization_id=organization_id,
            actor_id=actor_id,
            properties={
                "action": result.action.value,
                "risk_level": result.assessment.level.value,
                "triggered_rules": result.assessment.triggered_rules,
                "context": context,
            },
        )

    async def log_escalation(
        self,
        assessment: RiskAssessment,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Log a crisis escalation event."""
        await self._publisher.publish(
            event_name="safety.escalation_created",
            category=EventCategory.CLINICAL,
            organization_id=organization_id,
            actor_id=actor_id,
            properties={
                "risk_level": assessment.level.value,
                "triggered_rules": assessment.triggered_rules,
            },
        )
