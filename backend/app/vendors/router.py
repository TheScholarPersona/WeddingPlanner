import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.authz.deps import DbSession, OrgContext, require
from app.authz.permissions import Perm
from app.vendors import service
from app.vendors.schemas import CategoryT, VendorIn, VendorOut, VendorUpdateIn

router = APIRouter(prefix="/orgs/{org_id}/vendors", tags=["vendors"])


@router.get("", response_model=list[VendorOut])
async def list_vendors(
    db: DbSession,
    ctx: OrgContext = require(Perm.VENDORS_READ),
    category: CategoryT | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[VendorOut]:
    return await service.list_vendors(db, category, q)


@router.post("", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    body: VendorIn, db: DbSession, ctx: OrgContext = require(Perm.VENDORS_WRITE)
) -> VendorOut:
    return await service.create_vendor(db, ctx, body)


@router.get("/{vendor_id}", response_model=VendorOut)
async def get_vendor(
    vendor_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.VENDORS_READ)
) -> VendorOut:
    return await service.get_vendor(db, vendor_id)


@router.patch("/{vendor_id}", response_model=VendorOut)
async def update_vendor(
    vendor_id: uuid.UUID,
    body: VendorUpdateIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.VENDORS_WRITE),
) -> VendorOut:
    return await service.update_vendor(db, ctx, vendor_id, body)


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(
    vendor_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.VENDORS_WRITE)
) -> None:
    await service.delete_vendor(db, ctx, vendor_id)
