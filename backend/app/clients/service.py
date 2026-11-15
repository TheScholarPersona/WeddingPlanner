import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.authz.deps import OrgContext, not_found
from app.clients.models import Client, ClientContact
from app.clients.schemas import (
    ClientDetailOut,
    ClientIn,
    ClientOut,
    ClientProjectOut,
    ClientUpdateIn,
    ContactIn,
    ContactOut,
    ContactUpdateIn,
)
from app.core.errors import ProblemError
from app.projects.models import Project


def _contact_name(c: ClientContact) -> str:
    return " ".join(part for part in (c.first_name, c.last_name) if part)


def _contact_out(c: ClientContact) -> ContactOut:
    return ContactOut(
        id=c.id,
        first_name=c.first_name,
        last_name=c.last_name,
        email=c.email,
        phone=c.phone,
        role=c.role,
        is_primary=c.is_primary,
        has_portal_access=c.user_id is not None,
    )


async def _get(db: AsyncSession, client_id: uuid.UUID) -> Client:
    client = await db.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise not_found()
    return client


async def list_clients(
    db: AsyncSession, status: str | None = None, q: str | None = None
) -> list[ClientOut]:
    primary = (
        select(
            ClientContact.client_id,
            ClientContact.first_name,
            ClientContact.last_name,
            ClientContact.email,
        )
        .where(ClientContact.is_primary.is_(True))
        .ext(distinct_on(ClientContact.client_id))
        .subquery()
    )
    projects = (
        select(
            Project.client_id,
            func.count().label("project_count"),
            func.min(Project.wedding_date)
            .filter(Project.wedding_date >= func.current_date())
            .label("next_date"),
        )
        .where(Project.deleted_at.is_(None))
        .group_by(Project.client_id)
        .subquery()
    )
    stmt = (
        select(Client, primary, projects.c.project_count, projects.c.next_date)
        .outerjoin(primary, primary.c.client_id == Client.id)
        .outerjoin(projects, projects.c.client_id == Client.id)
        .where(Client.deleted_at.is_(None))
        .order_by(projects.c.next_date.asc().nulls_last(), Client.display_name)
    )
    if status:
        stmt = stmt.where(Client.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Client.display_name.ilike(like), primary.c.email.ilike(like)))
    rows = (await db.execute(stmt)).all()
    return [
        ClientOut(
            id=row.Client.id,
            display_name=row.Client.display_name,
            status=row.Client.status,
            source=row.Client.source,
            primary_contact=" ".join(p for p in (row.first_name, row.last_name) if p) or None,
            primary_email=row.email,
            next_wedding_date=row.next_date,
            project_count=row.project_count or 0,
            created_at=row.Client.created_at,
        )
        for row in rows
    ]


async def get_client(db: AsyncSession, client_id: uuid.UUID) -> ClientDetailOut:
    client = await _get(db, client_id)
    contacts = list(
        (
            await db.execute(
                select(ClientContact)
                .where(ClientContact.client_id == client.id)
                .order_by(ClientContact.is_primary.desc(), ClientContact.created_at)
            )
        ).scalars()
    )
    projects = list(
        (
            await db.execute(
                select(Project)
                .where(Project.client_id == client.id, Project.deleted_at.is_(None))
                .order_by(Project.wedding_date)
            )
        ).scalars()
    )
    primary = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)
    today = datetime.now(UTC).date()
    upcoming = [p.wedding_date for p in projects if p.wedding_date and p.wedding_date >= today]
    return ClientDetailOut(
        id=client.id,
        display_name=client.display_name,
        status=client.status,
        source=client.source,
        primary_contact=_contact_name(primary) if primary else None,
        primary_email=primary.email if primary else None,
        next_wedding_date=min(upcoming) if upcoming else None,
        project_count=len(projects),
        created_at=client.created_at,
        notes_internal=client.notes_internal,
        contacts=[_contact_out(c) for c in contacts],
        projects=[
            ClientProjectOut(id=p.id, title=p.title, wedding_date=p.wedding_date, status=p.status)
            for p in projects
        ],
    )


async def create_client(db: AsyncSession, ctx: OrgContext, body: ClientIn) -> Client:
    client = Client(
        organization_id=ctx.organization_id,
        display_name=body.display_name.strip(),
        status=body.status,
        source=body.source,
        notes_internal=body.notes_internal,
        created_by=ctx.user.id,
    )
    db.add(client)
    await db.flush()
    for index, contact in enumerate(body.contacts):
        data = contact.model_dump()
        data["is_primary"] = data["is_primary"] or (
            index == 0 and not any(c.is_primary for c in body.contacts)
        )
        db.add(ClientContact(organization_id=ctx.organization_id, client_id=client.id, **data))
    await db.flush()
    await audit.record(
        db,
        action="client.created",
        resource_type="client",
        resource_id=client.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return client


async def update_client(
    db: AsyncSession, ctx: OrgContext, client_id: uuid.UUID, body: ClientUpdateIn
) -> ClientDetailOut:
    client = await _get(db, client_id)
    fields = body.model_dump(exclude_unset=True)
    before = {k: getattr(client, k) for k in fields}
    for key, value in fields.items():
        if value is not None or key in {"source", "notes_internal"}:
            setattr(client, key, value)
    changes = audit.diff(before, {k: getattr(client, k) for k in fields})
    changes.pop("notes_internal", None)  # free text may contain personal data
    if changes or "notes_internal" in fields:
        await audit.record(
            db,
            action="client.updated",
            resource_type="client",
            resource_id=client.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes=changes,
        )
    await db.flush()
    return await get_client(db, client.id)


async def delete_client(db: AsyncSession, ctx: OrgContext, client_id: uuid.UUID) -> None:
    client = await _get(db, client_id)
    active = (
        await db.execute(
            select(func.count())
            .select_from(Project)
            .where(Project.client_id == client.id, Project.deleted_at.is_(None))
        )
    ).scalar_one()
    if active:
        raise ProblemError(
            409,
            "client_has_projects",
            "Client has weddings",
            "Archive or delete this client's weddings first.",
        )
    client.deleted_at = datetime.now(UTC)
    await audit.record(
        db,
        action="client.deleted",
        resource_type="client",
        resource_id=client.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


async def _set_primary(db: AsyncSession, client_id: uuid.UUID, primary_id: uuid.UUID) -> None:
    others = (
        await db.execute(
            select(ClientContact).where(
                ClientContact.client_id == client_id, ClientContact.id != primary_id
            )
        )
    ).scalars()
    for other in others:
        other.is_primary = False


async def add_contact(
    db: AsyncSession, ctx: OrgContext, client_id: uuid.UUID, body: ContactIn
) -> ContactOut:
    client = await _get(db, client_id)
    contact = ClientContact(
        organization_id=ctx.organization_id, client_id=client.id, **body.model_dump()
    )
    db.add(contact)
    await db.flush()
    if contact.is_primary:
        await _set_primary(db, client.id, contact.id)
    await audit.record(
        db,
        action="client_contact.created",
        resource_type="client_contact",
        resource_id=contact.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return _contact_out(contact)


async def _get_contact(
    db: AsyncSession, client_id: uuid.UUID, contact_id: uuid.UUID
) -> ClientContact:
    await _get(db, client_id)
    contact = await db.get(ClientContact, contact_id)
    if contact is None or contact.client_id != client_id:
        raise not_found()
    return contact


async def update_contact(
    db: AsyncSession,
    ctx: OrgContext,
    client_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ContactUpdateIn,
) -> ContactOut:
    contact = await _get_contact(db, client_id, contact_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key in {"last_name", "email", "phone"}:
            setattr(contact, key, value)
    await db.flush()
    if contact.is_primary:
        await _set_primary(db, client_id, contact.id)
    await audit.record(
        db,
        action="client_contact.updated",
        resource_type="client_contact",
        resource_id=contact.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return _contact_out(contact)


async def delete_contact(
    db: AsyncSession, ctx: OrgContext, client_id: uuid.UUID, contact_id: uuid.UUID
) -> None:
    contact = await _get_contact(db, client_id, contact_id)
    await db.delete(contact)
    await audit.record(
        db,
        action="client_contact.deleted",
        resource_type="client_contact",
        resource_id=contact_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
