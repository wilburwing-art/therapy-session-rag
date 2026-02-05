"""Service for consent management."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.models.db.consent import Consent, ConsentStatus, ConsentType
from src.models.domain.consent import (
    ConsentAuditEntry,
    ConsentCheck,
    ConsentGrant,
    ConsentRead,
    ConsentRevoke,
)
from src.models.domain.consent import ConsentStatus as DomainConsentStatus
from src.models.domain.consent import ConsentType as DomainConsentType
from src.repositories.consent_repo import ConsentRepository


class ConsentService:
    """Service for managing patient consent."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ConsentRepository(session)

    async def grant_consent(
        self,
        grant: ConsentGrant,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ConsentRead:
        """Grant consent for a patient.

        Creates a new consent record with status='granted'.
        If consent already exists and is active, raises ConflictError.

        Args:
            grant: The consent grant request
            ip_address: Optional IP address of the request
            user_agent: Optional user agent of the request

        Returns:
            The created consent record

        Raises:
            ConflictError: If active consent already exists for this patient/type
        """
        # Convert domain enum to db enum
        db_consent_type = ConsentType(grant.consent_type.value)

        # Check if active consent already exists
        existing = await self.repo.get_active_consent(
            patient_id=grant.patient_id,
            therapist_id=grant.therapist_id,
            consent_type=db_consent_type,
        )
        if existing:
            raise ConflictError(
                detail=f"Active consent already exists for type '{grant.consent_type.value}'"
            )

        # Create new consent record
        consent = Consent(
            patient_id=grant.patient_id,
            therapist_id=grant.therapist_id,
            consent_type=db_consent_type,
            status=ConsentStatus.GRANTED,
            granted_at=datetime.now(UTC),
            ip_address=ip_address,
            user_agent=user_agent,
            consent_metadata=grant.consent_metadata,
        )
        created = await self.repo.create(consent)
        return self._to_consent_read(created)

    async def revoke_consent(
        self,
        revoke: ConsentRevoke,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ConsentRead:
        """Revoke consent for a patient.

        Creates a new consent record with status='revoked'.
        Sets revoked_at timestamp on the record.

        Args:
            revoke: The consent revoke request
            ip_address: Optional IP address of the request
            user_agent: Optional user agent of the request

        Returns:
            The created revocation record

        Raises:
            NotFoundError: If no active consent exists to revoke
        """
        # Convert domain enum to db enum
        db_consent_type = ConsentType(revoke.consent_type.value)

        # Check if active consent exists
        existing = await self.repo.get_active_consent(
            patient_id=revoke.patient_id,
            therapist_id=revoke.therapist_id,
            consent_type=db_consent_type,
        )
        if not existing:
            raise NotFoundError(
                resource="Consent",
                detail=f"No active consent exists for type '{revoke.consent_type.value}'",
            )

        # Create new revocation record (immutable pattern)
        now = datetime.now(UTC)
        consent = Consent(
            patient_id=revoke.patient_id,
            therapist_id=revoke.therapist_id,
            consent_type=db_consent_type,
            status=ConsentStatus.REVOKED,
            granted_at=existing.granted_at,  # Preserve original grant time
            revoked_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
            consent_metadata=revoke.consent_metadata,
        )
        created = await self.repo.create(consent)
        return self._to_consent_read(created)

    async def check_consent(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_type: DomainConsentType,
    ) -> ConsentCheck:
        """Check if consent is currently active.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID
            consent_type: The type of consent to check

        Returns:
            ConsentCheck with has_consent flag and consent record if active
        """
        db_consent_type = ConsentType(consent_type.value)
        consent = await self.repo.get_active_consent(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_type=db_consent_type,
        )
        return ConsentCheck(
            patient_id=patient_id,
            consent_type=consent_type,
            has_consent=consent is not None,
            consent=self._to_consent_read(consent) if consent else None,
        )

    async def get_audit_log(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
        consent_type: DomainConsentType | None = None,
    ) -> list[ConsentAuditEntry]:
        """Get the complete consent history for a patient.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID
            consent_type: Optional filter by consent type

        Returns:
            List of all consent audit entries, ordered by granted_at descending
        """
        db_consent_type = (
            ConsentType(consent_type.value) if consent_type else None
        )
        consents = await self.repo.get_audit_log(
            patient_id=patient_id,
            therapist_id=therapist_id,
            consent_type=db_consent_type,
        )
        return [self._to_audit_entry(c) for c in consents]

    async def get_all_active(
        self,
        patient_id: uuid.UUID,
        therapist_id: uuid.UUID,
    ) -> list[ConsentRead]:
        """Get all active consents for a patient.

        Args:
            patient_id: The patient's user ID
            therapist_id: The therapist's user ID

        Returns:
            List of all active consent records
        """
        consents = await self.repo.get_all_active_for_patient(
            patient_id=patient_id,
            therapist_id=therapist_id,
        )
        return [self._to_consent_read(c) for c in consents]

    def _to_consent_read(self, consent: Consent) -> ConsentRead:
        """Convert a Consent DB model to ConsentRead schema."""
        return ConsentRead(
            id=consent.id,
            patient_id=consent.patient_id,
            therapist_id=consent.therapist_id,
            consent_type=DomainConsentType(consent.consent_type.value),
            status=DomainConsentStatus(consent.status.value),
            granted_at=consent.granted_at,
            revoked_at=consent.revoked_at,
            ip_address=consent.ip_address,
            user_agent=consent.user_agent,
            consent_metadata=consent.consent_metadata,
        )

    def _to_audit_entry(self, consent: Consent) -> ConsentAuditEntry:
        """Convert a Consent DB model to ConsentAuditEntry schema."""
        return ConsentAuditEntry(
            id=consent.id,
            consent_type=DomainConsentType(consent.consent_type.value),
            status=DomainConsentStatus(consent.status.value),
            granted_at=consent.granted_at,
            revoked_at=consent.revoked_at,
            ip_address=consent.ip_address,
            user_agent=consent.user_agent,
        )
