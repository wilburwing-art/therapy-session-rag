"""Repository for consent operations."""

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.db.consent import Consent, ConsentStatus, ConsentType


class ConsentRepository:
    """Repository for consent database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, consent: Consent) -> Consent:
        """Create a new consent record.

        Args:
            consent: The consent record to create

        Returns:
            The created consent record
        """
        self.session.add(consent)
        await self.session.flush()
        await self.session.refresh(consent)
        return consent

    async def get_latest_consent(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_type: ConsentType,
    ) -> Consent | None:
        """Get the most recent consent record for a patient/therapist/type combination.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID
            consent_type: The type of consent

        Returns:
            The most recent consent record, or None if no consent exists
        """
        result = await self.session.execute(
            select(Consent)
            .where(
                and_(
                    Consent.patient_id == patient_id,
                    Consent.therapist_id == therapist_id,
                    Consent.consent_type == consent_type,
                )
            )
            .order_by(Consent.granted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_consent(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_type: ConsentType,
    ) -> Consent | None:
        """Get the active consent record for a patient/therapist/type combination.

        A consent is active if the most recent record has status='granted'.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID
            consent_type: The type of consent

        Returns:
            The active consent record, or None if no active consent exists
        """
        latest = await self.get_latest_consent(patient_id, therapist_id, consent_type)
        if latest and latest.status == ConsentStatus.GRANTED:
            return latest
        return None

    async def get_audit_log(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_type: ConsentType | None = None,
    ) -> list[Consent]:
        """Get all consent records for a patient/therapist combination.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID
            consent_type: Optional filter by consent type

        Returns:
            List of all consent records, ordered by granted_at descending
        """
        conditions = [
            Consent.patient_id == patient_id,
            Consent.therapist_id == therapist_id,
        ]
        if consent_type is not None:
            conditions.append(Consent.consent_type == consent_type)

        result = await self.session.execute(
            select(Consent)
            .where(and_(*conditions))
            .order_by(Consent.granted_at.desc())
        )
        return list(result.scalars().all())

    async def get_all_active_for_patient(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> list[Consent]:
        """Get all active consents for a patient/therapist combination.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID

        Returns:
            List of active consent records (one per consent type, if active)
        """
        active_consents: list[Consent] = []
        for consent_type in ConsentType:
            consent = await self.get_active_consent(
                patient_id, therapist_id, consent_type
            )
            if consent:
                active_consents.append(consent)
        return active_consents
