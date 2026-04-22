"""Intake service.

Issue, list, revoke intake invitations; load and submit them from the
public patient endpoint. Tokens are stored hashed and returned once at
issue time so the therapist can copy the URL if email delivery fails.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from src.models.db.intake_form import IntakeForm, IntakeFormStatus
from src.models.db.intake_invitation import (
    IntakeInvitation,
    IntakeInvitationStatus,
)
from src.models.db.intake_response import IntakeResponse
from src.repositories.intake_repo import (
    IntakeFormRepository,
    IntakeInvitationRepository,
    IntakeResponseRepository,
)

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32
_INVITATION_TTL = timedelta(days=14)


class IntakeService:
    """Manage intake forms, invitations, and responses."""

    def __init__(
        self,
        db_session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.db_session = db_session
        self.settings = settings or get_settings()
        self.form_repo = IntakeFormRepository(db_session)
        self.invitation_repo = IntakeInvitationRepository(db_session)
        self.response_repo = IntakeResponseRepository(db_session)

    async def create_form(
        self,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        name: str,
        description: str | None,
        questions: list[dict[str, Any]],
    ) -> IntakeForm:
        return await self.form_repo.create(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            questions=questions,
        )

    async def update_form(
        self,
        organization_id: uuid.UUID,
        form_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        status: IntakeFormStatus | None = None,
        questions: list[dict[str, Any]] | None = None,
    ) -> IntakeForm:
        form = await self.form_repo.get_by_id_for_org(form_id, organization_id)
        if form is None:
            raise NotFoundError(resource="IntakeForm", resource_id=str(form_id))
        return await self.form_repo.update(
            form,
            name=name,
            description=description,
            status=status,
            questions=questions,
        )

    async def get_form(
        self,
        organization_id: uuid.UUID,
        form_id: uuid.UUID,
    ) -> IntakeForm:
        form = await self.form_repo.get_by_id_for_org(form_id, organization_id)
        if form is None:
            raise NotFoundError(resource="IntakeForm", resource_id=str(form_id))
        return form

    async def list_forms(
        self, organization_id: uuid.UUID
    ) -> list[IntakeForm]:
        return await self.form_repo.list_for_org(organization_id)

    async def issue_invitation(
        self,
        organization_id: uuid.UUID,
        invited_by_user_id: uuid.UUID,
        form_id: uuid.UUID,
        patient_email: str,
        patient_name: str | None,
    ) -> tuple[IntakeInvitation, str, datetime]:
        """Issue an intake invitation.

        Verifies the form belongs to the same org and is not archived.
        Rejects if a pending invitation already exists for this
        (org, email).

        Returns (invitation, raw_token, expires_at). Persist only the
        hashed token; the raw token goes to the patient.
        """
        normalized_email = patient_email.lower().strip()

        form = await self.form_repo.get_by_id_for_org(form_id, organization_id)
        if form is None:
            raise NotFoundError(resource="IntakeForm", resource_id=str(form_id))
        if form.status == IntakeFormStatus.ARCHIVED:
            raise ConflictError(
                detail="Cannot send invitations for an archived form"
            )

        pending = await self.invitation_repo.get_pending_for_org_and_email(
            organization_id=organization_id,
            patient_email=normalized_email,
        )
        if pending is not None:
            raise ConflictError(
                detail="A pending intake invitation already exists for this email"
            )

        raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
        token_hash = self._hash_token(raw_token)
        expires_at = datetime.now(UTC) + _INVITATION_TTL

        invitation = await self.invitation_repo.create(
            organization_id=organization_id,
            form_id=form_id,
            invited_by_user_id=invited_by_user_id,
            patient_email=normalized_email,
            patient_name=patient_name,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        logger.info(
            "Intake invitation issued: org=%s invitee=%s form=%s expires=%s",
            organization_id,
            normalized_email,
            form_id,
            expires_at.isoformat(),
        )
        return invitation, raw_token, expires_at

    async def list_invitations(
        self, organization_id: uuid.UUID
    ) -> list[IntakeInvitation]:
        return await self.invitation_repo.list_for_org(organization_id)

    async def list_invitations_for_email(
        self,
        organization_id: uuid.UUID,
        patient_email: str,
    ) -> list[IntakeInvitation]:
        return await self.invitation_repo.list_for_org_and_email(
            organization_id=organization_id,
            patient_email=patient_email.lower().strip(),
        )

    async def revoke_invitation(
        self,
        organization_id: uuid.UUID,
        invitation_id: uuid.UUID,
    ) -> None:
        """Revoke a pending invitation. Submitted invitations cannot be revoked."""
        invitation = await self.invitation_repo.get_by_id_for_org(
            invitation_id, organization_id
        )
        if invitation is None:
            raise NotFoundError(
                resource="IntakeInvitation",
                resource_id=str(invitation_id),
            )
        if invitation.status == IntakeInvitationStatus.SUBMITTED:
            raise ConflictError(
                detail="Cannot revoke an invitation that has been submitted"
            )
        if invitation.status == IntakeInvitationStatus.REVOKED:
            return
        await self.invitation_repo.mark_revoked(invitation_id)
        logger.info(
            "Intake invitation %s revoked by org %s",
            invitation_id,
            organization_id,
        )

    async def load_public_invitation(
        self, raw_token: str
    ) -> tuple[IntakeInvitation, IntakeForm]:
        """Resolve a raw token to (invitation, form) for the public redeem page.

        Raises UnauthorizedError for any invalid, expired, submitted, or
        revoked invitation — callers must not disclose which case it is.
        """
        token_hash = self._hash_token(raw_token)
        invitation = await self.invitation_repo.get_by_token_hash(token_hash)
        generic = UnauthorizedError("Invalid or expired intake invitation")
        if invitation is None:
            raise generic
        if invitation.status != IntakeInvitationStatus.PENDING:
            logger.info(
                "Intake invitation %s not pending (status=%s)",
                invitation.id,
                invitation.status.value,
            )
            raise generic
        if invitation.expires_at <= datetime.now(UTC):
            logger.info("Intake invitation %s expired", invitation.id)
            raise generic

        form = invitation.form
        if form is None:
            form = await self.form_repo.get_by_id(invitation.form_id)
        if form is None:
            raise NotFoundError(
                resource="IntakeForm",
                resource_id=str(invitation.form_id),
            )
        return invitation, form

    async def submit_response(
        self,
        raw_token: str,
        answers: dict[str, Any],
        submitted_ip: str | None = None,
        submitted_user_agent: str | None = None,
    ) -> IntakeResponse:
        """Record a patient's intake submission.

        Validates answer keys against the form's question ids and
        enforces ``required=True``. Marks the invitation submitted as
        part of the same unit of work — the endpoint commits the
        surrounding DB session.
        """
        invitation, form = await self.load_public_invitation(raw_token)

        self._validate_answers(questions=form.questions, answers=answers)

        now = datetime.now(UTC)
        response = await self.response_repo.create(
            invitation_id=invitation.id,
            form_id=form.id,
            organization_id=invitation.organization_id,
            answers=answers,
            submitted_ip=submitted_ip,
            submitted_user_agent=submitted_user_agent,
            submitted_at=now,
        )
        await self.invitation_repo.mark_submitted(invitation.id)
        logger.info(
            "Intake response recorded for invitation %s (form=%s)",
            invitation.id,
            form.id,
        )
        return response

    async def render_intake_context_for_email(
        self,
        organization_id: uuid.UUID,
        patient_email: str,
    ) -> str | None:
        """Render the patient's most recent intake submission as recap context.

        Returns None if the patient has no submitted intake responses in
        this organization. The output is a compact, human-readable
        markdown block suitable for prepending to a recap prompt.
        """
        responses = await self.response_repo.list_for_org_and_email(
            organization_id=organization_id,
            patient_email=patient_email.lower().strip(),
        )
        if not responses:
            return None

        latest = responses[0]
        form = await self.form_repo.get_by_id(latest.form_id)
        if form is None:
            return None

        lines: list[str] = [
            f"Intake form: {form.name}",
            f"Submitted: {latest.submitted_at.isoformat()}",
            "",
        ]
        for question in form.questions:
            qid = question.get("id")
            if not isinstance(qid, str):
                continue
            prompt = question.get("prompt", qid)
            answer = latest.answers.get(qid)
            if answer is None:
                continue
            lines.append(f"- {prompt}: {self._format_answer(answer)}")
        return "\n".join(lines)

    @staticmethod
    def _validate_answers(
        questions: list[dict[str, Any]],
        answers: dict[str, Any],
    ) -> None:
        """Reject answers that miss required questions or reference unknowns."""
        known_ids: set[str] = set()
        required_ids: set[str] = set()
        for question in questions:
            qid = question.get("id")
            if not isinstance(qid, str) or not qid:
                continue
            known_ids.add(qid)
            if question.get("required", True):
                required_ids.add(qid)

        unknown = set(answers.keys()) - known_ids
        if unknown:
            raise ConflictError(
                detail=f"Unknown question id(s): {sorted(unknown)}"
            )

        missing: list[str] = []
        for qid in required_ids:
            value = answers.get(qid)
            if value is None:
                missing.append(qid)
                continue
            if isinstance(value, str) and not value.strip():
                missing.append(qid)
                continue
            if isinstance(value, list) and len(value) == 0:
                missing.append(qid)
        if missing:
            raise ConflictError(
                detail=f"Missing required answers: {sorted(missing)}"
            )

    @staticmethod
    def _format_answer(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
