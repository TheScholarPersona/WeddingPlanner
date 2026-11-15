import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.authz.deps import DbSession, OrgContext, require
from app.authz.permissions import Perm
from app.clients import service
from app.clients.schemas import (
    ClientDetailOut,
    ClientIn,
    ClientOut,
    ClientStatusT,
    ClientUpdateIn,
    ContactIn,
    ContactOut,
    ContactUpdateIn,
)

router = APIRouter(prefix="/orgs/{org_id}/clients", tags=["clients"])


@router.get("", response_model=list[ClientOut])
async def list_clients(
    db: DbSession,
    ctx: OrgContext = require(Perm.CLIENTS_READ),
    status: ClientStatusT | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[ClientOut]:
    return await service.list_clients(db, status, q)


@router.post("", response_model=ClientDetailOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientIn, db: DbSession, ctx: OrgContext = require(Perm.CLIENTS_WRITE)
) -> ClientDetailOut:
    client = await service.create_client(db, ctx, body)
    return await service.get_client(db, client.id)


@router.get("/{client_id}", response_model=ClientDetailOut)
async def get_client(
    client_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.CLIENTS_READ)
) -> ClientDetailOut:
    return await service.get_client(db, client_id)


@router.patch("/{client_id}", response_model=ClientDetailOut)
async def update_client(
    client_id: uuid.UUID,
    body: ClientUpdateIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.CLIENTS_WRITE),
) -> ClientDetailOut:
    return await service.update_client(db, ctx, client_id, body)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    client_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.CLIENTS_DELETE)
) -> None:
    await service.delete_client(db, ctx, client_id)


@router.post(
    "/{client_id}/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED
)
async def add_contact(
    client_id: uuid.UUID,
    body: ContactIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.CLIENTS_WRITE),
) -> ContactOut:
    return await service.add_contact(db, ctx, client_id, body)


@router.patch("/{client_id}/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(
    client_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ContactUpdateIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.CLIENTS_WRITE),
) -> ContactOut:
    return await service.update_contact(db, ctx, client_id, contact_id, body)


@router.delete("/{client_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    client_id: uuid.UUID,
    contact_id: uuid.UUID,
    db: DbSession,
    ctx: OrgContext = require(Perm.CLIENTS_WRITE),
) -> None:
    await service.delete_contact(db, ctx, client_id, contact_id)
