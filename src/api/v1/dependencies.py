"""FastAPI dependencies for API v1."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.exceptions import UnauthorizedError
from src.core.security import is_valid_api_key_format, verify_api_key
from src.models.db.api_key import ApiKey
from src.repositories.api_key_repo import ApiKeyRepository


@dataclass
class AuthContext:
    """Authentication context containing validated API key info."""

    api_key_id: uuid.UUID
    organization_id: uuid.UUID
    api_key_name: str


async def get_api_key_auth(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    session: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """Validate API key and return authentication context.

    Args:
        x_api_key: The API key from X-API-Key header
        session: Database session

    Returns:
        AuthContext with validated API key information

    Raises:
        UnauthorizedError: If API key is missing, invalid, or inactive
    """
    if not x_api_key:
        raise UnauthorizedError("API key required. Provide X-API-Key header.")

    if not is_valid_api_key_format(x_api_key):
        raise UnauthorizedError("Invalid API key format.")

    # Find all active API keys and check against each
    # This is necessary because we store hashed keys
    result = await session.execute(
        select(ApiKey).where(ApiKey.is_active == True)  # noqa: E712
    )
    active_keys = result.scalars().all()

    for api_key in active_keys:
        if verify_api_key(x_api_key, api_key.key_hash):
            # Update last_used_at
            repo = ApiKeyRepository(session)
            await repo.update_last_used(api_key.id)

            return AuthContext(
                api_key_id=api_key.id,
                organization_id=api_key.organization_id,
                api_key_name=api_key.name,
            )

    raise UnauthorizedError("Invalid API key.")


# Type alias for dependency injection
Auth = Annotated[AuthContext, Depends(get_api_key_auth)]
