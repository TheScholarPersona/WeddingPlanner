import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.admin import service
from app.admin.schemas import (
    AdminOrganizationCreatedOut,
    AdminOrganizationIn,
    AdminOrganizationOut,
    ResetTwoFactorIn,
    SupportGrantIn,
    SupportGrantOut,
    SupportViewOut,
)
from app.authz.deps import (
    TWO_FACTOR_REQUIRED,
    Authenticated,
    CurrentUser,
    DbSession,
    OrgContext,
    not_found,
    require,
    require_recent_auth,
)
from app.authz.permissions import Perm


async def platform_admin(auth: CurrentUser) -> Authenticated:
    """Platform admins only, and only with two-factor authentication on."""
    if not auth.user.is_platform_admin:
        raise not_found()
    if not auth.user.two_factor_enabled:
        raise TWO_FACTOR_REQUIRED
    return auth


Admin = Annotated[Authenticated, Depends(platform_admin)]
router = APIRouter(tags=["admin"])


@router.get("/admin/organizations", response_model=list[AdminOrganizationOut])
async def organizations(admin: Admin, db: DbSession) -> list[AdminOrganizationOut]:
    return await service.list_organizations(db)


@router.post("/admin/organizations", response_model=AdminOrganizationCreatedOut, status_code=201)
async def create_organization(
    body: AdminOrganizationIn, admin: Admin, db: DbSession
) -> AdminOrganizationCreatedOut:
    return await service.create(db, admin, body)


@router.post("/admin/organizations/{org_id}/suspend", response_model=AdminOrganizationOut)
async def suspend(org_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminOrganizationOut:
    return await service.set_status(db, admin, org_id, "suspended")


@router.post("/admin/organizations/{org_id}/reactivate", response_model=AdminOrganizationOut)
async def reactivate(org_id: uuid.UUID, admin: Admin, db: DbSession) -> AdminOrganizationOut:
    return await service.set_status(db, admin, org_id, "active")


@router.get("/admin/organizations/{org_id}/support", response_model=SupportViewOut)
async def support_view(org_id: uuid.UUID, admin: Admin, db: DbSession) -> SupportViewOut:
    return await service.support_view(db, admin, org_id)


@router.post("/admin/users/reset-2fa", status_code=status.HTTP_204_NO_CONTENT)
async def reset_two_factor(body: ResetTwoFactorIn, admin: Admin, db: DbSession) -> None:
    await service.reset_two_factor(db, admin, body)


# --- Organization side ----------------------------------------------------------------------

G = "/orgs/{org_id}/support-access"


@router.get(G, response_model=list[SupportGrantOut])
async def list_grants(
    db: DbSession, ctx: OrgContext = require(Perm.SUPPORT_ACCESS)
) -> list[SupportGrantOut]:
    return await service.list_grants(db, ctx)


@router.post(G, response_model=SupportGrantOut, status_code=status.HTTP_201_CREATED)
async def grant(
    body: SupportGrantIn, db: DbSession, ctx: OrgContext = require(Perm.SUPPORT_ACCESS)
) -> SupportGrantOut:
    require_recent_auth(ctx)
    return await service.grant(db, ctx, body)


@router.delete(G + "/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    grant_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.SUPPORT_ACCESS)
) -> None:
    await service.revoke(db, ctx, grant_id)
