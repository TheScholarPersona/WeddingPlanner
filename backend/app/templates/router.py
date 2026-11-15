import uuid

from fastapi import APIRouter, status

from app.authz.deps import DbSession, OrgContext, require
from app.authz.permissions import Perm
from app.templates import service
from app.templates.schemas import (
    TemplateDetailOut,
    TemplateIn,
    TemplateItemIn,
    TemplateItemOut,
    TemplateItemUpdateIn,
    TemplateOut,
    TemplateUpdateIn,
)

router = APIRouter(prefix="/orgs/{org_id}/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    db: DbSession, ctx: OrgContext = require(Perm.TEMPLATES_READ)
) -> list[TemplateOut]:
    return await service.list_templates(db)


@router.post("", response_model=TemplateDetailOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateIn, db: DbSession, ctx: OrgContext = require(Perm.TEMPLATES_MANAGE)
) -> TemplateDetailOut:
    return await service.create_template(db, ctx, body)


@router.get("/{template_id}", response_model=TemplateDetailOut)
async def get_template(
    template_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.TEMPLATES_READ)
) -> TemplateDetailOut:
    return await service.get_template(db, template_id)


@router.patch("/{template_id}", response_model=TemplateDetailOut)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdateIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.TEMPLATES_MANAGE),
) -> TemplateDetailOut:
    return await service.update_template(db, ctx, template_id, body)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.TEMPLATES_MANAGE)
) -> None:
    await service.delete_template(db, ctx, template_id)


@router.post(
    "/{template_id}/items", response_model=TemplateItemOut, status_code=status.HTTP_201_CREATED
)
async def add_item(
    template_id: uuid.UUID,
    body: TemplateItemIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.TEMPLATES_MANAGE),
) -> TemplateItemOut:
    return await service.add_item(db, ctx, template_id, body)


@router.patch("/{template_id}/items/{item_id}", response_model=TemplateItemOut)
async def update_item(
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    body: TemplateItemUpdateIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.TEMPLATES_MANAGE),
) -> TemplateItemOut:
    return await service.update_item(db, template_id, item_id, body)


@router.delete("/{template_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    db: DbSession,
    ctx: OrgContext = require(Perm.TEMPLATES_MANAGE),
) -> None:
    await service.delete_item(db, template_id, item_id)
