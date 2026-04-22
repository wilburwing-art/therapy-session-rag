"""Operator panel endpoints.

All routes are gated by ``require_admin`` and are intentionally NOT
behind the billing entitlement dependency — an admin has to be able to
inspect a suspended practice.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.admin_gate import require_admin
from src.core.database import DbSession
from src.models.db.event import EventCategory
from src.models.db.user import User
from src.models.domain.organization import (
    AdminAuditEventPage,
    OrganizationAdminDetail,
    OrganizationAdminView,
)
from src.services.admin_service import AdminService

router = APIRouter()


def get_admin_service(session: DbSession) -> AdminService:
    return AdminService(session)


AdminSvc = Annotated[AdminService, Depends(get_admin_service)]
AdminUser = Annotated[User, Depends(require_admin)]


@router.get("/orgs", response_model=list[OrganizationAdminView])
async def list_orgs(
    service: AdminSvc,
    _admin: AdminUser,
) -> list[OrganizationAdminView]:
    """List every organization with rollup counts."""
    return await service.list_organizations()


@router.get("/orgs/{org_id}", response_model=OrganizationAdminDetail)
async def get_org_detail(
    org_id: uuid.UUID,
    service: AdminSvc,
    _admin: AdminUser,
) -> OrganizationAdminDetail:
    """Full admin detail for one organization."""
    return await service.get_organization_detail(org_id)


@router.post("/orgs/{org_id}/disable", status_code=200)
async def disable_org(
    org_id: uuid.UUID,
    service: AdminSvc,
    _admin: AdminUser,
) -> OrganizationAdminDetail:
    """Suspend an organization. Idempotent."""
    await service.disable_organization(org_id)
    return await service.get_organization_detail(org_id)


@router.post("/orgs/{org_id}/enable", status_code=200)
async def enable_org(
    org_id: uuid.UUID,
    service: AdminSvc,
    _admin: AdminUser,
) -> OrganizationAdminDetail:
    """Clear an organization's suspension. Idempotent."""
    await service.enable_organization(org_id)
    return await service.get_organization_detail(org_id)


@router.get("/events", response_model=AdminAuditEventPage)
async def list_audit_events(
    service: AdminSvc,
    _admin: AdminUser,
    category: Annotated[EventCategory | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AdminAuditEventPage:
    """Cross-tenant audit log with cursor pagination."""
    return await service.list_audit_events(
        category=category,
        actor_id=actor_id,
        since=since,
        until=until,
        cursor=cursor,
        limit=limit,
    )
