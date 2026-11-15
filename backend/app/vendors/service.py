import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.authz.deps import OrgContext, not_found
from app.projects.models import ProjectVendor
from app.vendors.models import Vendor
from app.vendors.schemas import VendorIn, VendorOut, VendorUpdateIn

NULLABLE = {"contact_name", "email", "phone", "website", "notes_internal", "rating"}


def _out(vendor: Vendor, project_count: int) -> VendorOut:
    return VendorOut(
        id=vendor.id,
        name=vendor.name,
        category=vendor.category,
        contact_name=vendor.contact_name,
        email=vendor.email,
        phone=vendor.phone,
        website=vendor.website,
        notes_internal=vendor.notes_internal,
        rating=vendor.rating,
        project_count=project_count,
    )


async def _get(db: AsyncSession, vendor_id: uuid.UUID) -> Vendor:
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None or vendor.deleted_at is not None:
        raise not_found()
    return vendor


async def _project_count(db: AsyncSession, vendor_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(ProjectVendor)
            .where(ProjectVendor.vendor_id == vendor_id)
        )
    ).scalar_one()


async def list_vendors(
    db: AsyncSession, category: str | None = None, q: str | None = None
) -> list[VendorOut]:
    counts = (
        select(ProjectVendor.vendor_id, func.count().label("n"))
        .group_by(ProjectVendor.vendor_id)
        .subquery()
    )
    stmt = (
        select(Vendor, counts.c.n)
        .outerjoin(counts, counts.c.vendor_id == Vendor.id)
        .where(Vendor.deleted_at.is_(None))
        .order_by(Vendor.category, Vendor.name)
    )
    if category:
        stmt = stmt.where(Vendor.category == category)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Vendor.name.ilike(like), Vendor.contact_name.ilike(like)))
    return [_out(v, n or 0) for v, n in (await db.execute(stmt)).all()]


async def get_vendor(db: AsyncSession, vendor_id: uuid.UUID) -> VendorOut:
    vendor = await _get(db, vendor_id)
    return _out(vendor, await _project_count(db, vendor.id))


async def create_vendor(db: AsyncSession, ctx: OrgContext, body: VendorIn) -> VendorOut:
    vendor = Vendor(organization_id=ctx.organization_id, **body.model_dump())
    db.add(vendor)
    await db.flush()
    await audit.record(
        db,
        action="vendor.created",
        resource_type="vendor",
        resource_id=vendor.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return _out(vendor, 0)


async def update_vendor(
    db: AsyncSession, ctx: OrgContext, vendor_id: uuid.UUID, body: VendorUpdateIn
) -> VendorOut:
    vendor = await _get(db, vendor_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key in NULLABLE:
            setattr(vendor, key, value)
    await db.flush()
    await audit.record(
        db,
        action="vendor.updated",
        resource_type="vendor",
        resource_id=vendor.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return _out(vendor, await _project_count(db, vendor.id))


async def delete_vendor(db: AsyncSession, ctx: OrgContext, vendor_id: uuid.UUID) -> None:
    vendor = await _get(db, vendor_id)
    vendor.deleted_at = datetime.now(UTC)
    await audit.record(
        db,
        action="vendor.deleted",
        resource_type="vendor",
        resource_id=vendor.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
