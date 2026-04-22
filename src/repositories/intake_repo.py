"""Repositories for intake forms, invitations, and responses."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.intake_form import IntakeForm, IntakeFormStatus
from src.models.db.intake_invitation import (
    IntakeInvitation,
    IntakeInvitationStatus,
)
from src.models.db.intake_response import IntakeResponse


class IntakeFormRepository:
    """Data access for intake form templates."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        name: str,
        description: str | None,
        questions: list[dict[str, Any]],
    ) -> IntakeForm:
        form = IntakeForm(
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            name=name,
            description=description,
            questions=questions,
        )
        self.session.add(form)
        await self.session.flush()
        await self.session.refresh(form)
        return form

    async def update(
        self,
        form: IntakeForm,
        *,
        name: str | None,
        description: str | None,
        status: IntakeFormStatus | None,
        questions: list[dict[str, Any]] | None,
    ) -> IntakeForm:
        if name is not None:
            form.name = name
        if description is not None:
            form.description = description
        if status is not None:
            form.status = status
        if questions is not None:
            form.questions = questions
        await self.session.flush()
        await self.session.refresh(form)
        return form

    async def get_by_id_for_org(
        self,
        form_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> IntakeForm | None:
        result = await self.session.execute(
            select(IntakeForm).where(
                IntakeForm.id == form_id,
                IntakeForm.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, form_id: uuid.UUID) -> IntakeForm | None:
        result = await self.session.execute(
            select(IntakeForm).where(IntakeForm.id == form_id)
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self, organization_id: uuid.UUID
    ) -> list[IntakeForm]:
        result = await self.session.execute(
            select(IntakeForm)
            .where(IntakeForm.organization_id == organization_id)
            .order_by(IntakeForm.created_at.desc())
        )
        return list(result.scalars().all())


class IntakeInvitationRepository:
    """Data access for intake invitations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        organization_id: uuid.UUID,
        form_id: uuid.UUID,
        invited_by_user_id: uuid.UUID,
        patient_email: str,
        patient_name: str | None,
        token_hash: str,
        expires_at: datetime,
    ) -> IntakeInvitation:
        invitation = IntakeInvitation(
            organization_id=organization_id,
            form_id=form_id,
            invited_by_user_id=invited_by_user_id,
            patient_email=patient_email,
            patient_name=patient_name,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(invitation)
        await self.session.flush()
        await self.session.refresh(invitation)
        return invitation

    async def get_by_token_hash(
        self, token_hash: str
    ) -> IntakeInvitation | None:
        result = await self.session.execute(
            select(IntakeInvitation).where(
                IntakeInvitation.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_org(
        self,
        invitation_id: uuid.UUID,
        organization_id: uuid.UUID,
    ) -> IntakeInvitation | None:
        result = await self.session.execute(
            select(IntakeInvitation).where(
                IntakeInvitation.id == invitation_id,
                IntakeInvitation.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_for_org_and_email(
        self,
        organization_id: uuid.UUID,
        patient_email: str,
    ) -> IntakeInvitation | None:
        """Return a pending, unexpired invitation for (org, email), if any."""
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(IntakeInvitation).where(
                IntakeInvitation.organization_id == organization_id,
                IntakeInvitation.patient_email == patient_email,
                IntakeInvitation.status == IntakeInvitationStatus.PENDING,
                IntakeInvitation.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self, organization_id: uuid.UUID
    ) -> list[IntakeInvitation]:
        result = await self.session.execute(
            select(IntakeInvitation)
            .where(IntakeInvitation.organization_id == organization_id)
            .order_by(IntakeInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_org_and_email(
        self,
        organization_id: uuid.UUID,
        patient_email: str,
    ) -> list[IntakeInvitation]:
        result = await self.session.execute(
            select(IntakeInvitation)
            .where(
                IntakeInvitation.organization_id == organization_id,
                IntakeInvitation.patient_email == patient_email,
            )
            .order_by(IntakeInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_submitted(self, invitation_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        await self.session.execute(
            update(IntakeInvitation)
            .where(IntakeInvitation.id == invitation_id)
            .values(
                status=IntakeInvitationStatus.SUBMITTED,
                submitted_at=now,
            )
        )

    async def mark_revoked(self, invitation_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        await self.session.execute(
            update(IntakeInvitation)
            .where(IntakeInvitation.id == invitation_id)
            .values(
                status=IntakeInvitationStatus.REVOKED,
                revoked_at=now,
            )
        )

    async def delete_pending(self, invitation_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(IntakeInvitation).where(
                IntakeInvitation.id == invitation_id,
                IntakeInvitation.status == IntakeInvitationStatus.PENDING,
            )
        )


class IntakeResponseRepository:
    """Data access for intake responses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        invitation_id: uuid.UUID,
        form_id: uuid.UUID,
        organization_id: uuid.UUID,
        answers: dict[str, Any],
        submitted_ip: str | None,
        submitted_user_agent: str | None,
        submitted_at: datetime,
    ) -> IntakeResponse:
        response = IntakeResponse(
            invitation_id=invitation_id,
            form_id=form_id,
            organization_id=organization_id,
            answers=answers,
            submitted_ip=submitted_ip,
            submitted_user_agent=submitted_user_agent,
            submitted_at=submitted_at,
        )
        self.session.add(response)
        await self.session.flush()
        await self.session.refresh(response)
        return response

    async def get_by_invitation_id(
        self, invitation_id: uuid.UUID
    ) -> IntakeResponse | None:
        result = await self.session.execute(
            select(IntakeResponse).where(
                IntakeResponse.invitation_id == invitation_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org_and_email(
        self,
        organization_id: uuid.UUID,
        patient_email: str,
    ) -> list[IntakeResponse]:
        """Return responses submitted by invitations matching (org, email).

        Joined through ``intake_invitations`` since responses only hold
        ``invitation_id``, not an email.
        """
        result = await self.session.execute(
            select(IntakeResponse)
            .join(
                IntakeInvitation,
                IntakeInvitation.id == IntakeResponse.invitation_id,
            )
            .where(
                IntakeResponse.organization_id == organization_id,
                IntakeInvitation.patient_email == patient_email,
            )
            .order_by(IntakeResponse.submitted_at.desc())
        )
        return list(result.scalars().all())
