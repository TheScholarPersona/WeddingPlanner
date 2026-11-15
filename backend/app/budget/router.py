import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Response, status

from app.authz.deps import DbSession, ProjectContext, require_project
from app.authz.permissions import ProjectPerm
from app.budget import service
from app.budget.schemas import (
    BudgetOut,
    BudgetUpdateIn,
    CategoryIn,
    CategoryUpdateIn,
    ItemIn,
    ItemUpdateIn,
    PaymentIn,
    PaymentUpdateIn,
)

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}/budget", tags=["budget"])
IfMatch = Annotated[str | None, Header()]


def _etag(response: Response, budget: BudgetOut) -> BudgetOut:
    response.headers["ETag"] = f'"{budget.version}"'
    return budget


@router.get("", response_model=BudgetOut)
async def get_budget(
    response: Response,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_READ),
) -> BudgetOut:
    return _etag(response, await service.get_budget(db, ctx))


@router.patch("", response_model=BudgetOut)
async def update_budget(
    body: BudgetUpdateIn,
    response: Response,
    db: DbSession,
    if_match: IfMatch = None,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_SET_TOTAL),
) -> BudgetOut:
    return _etag(response, await service.update_budget(db, ctx, body, if_match))


@router.post("/categories", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def add_category(
    body: CategoryIn, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE)
) -> BudgetOut:
    return await service.add_category(db, ctx, body)


@router.patch("/categories/{category_id}", response_model=BudgetOut)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> BudgetOut:
    return await service.update_category(db, ctx, category_id, body)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> None:
    await service.delete_category(db, ctx, category_id)


@router.post("/items", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def add_item(
    body: ItemIn, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE)
) -> BudgetOut:
    return await service.add_item(db, ctx, body)


@router.patch("/items/{item_id}", response_model=BudgetOut)
async def update_item(
    item_id: uuid.UUID,
    body: ItemUpdateIn,
    db: DbSession,
    if_match: IfMatch = None,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> BudgetOut:
    return await service.update_item(db, ctx, item_id, body, if_match)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> None:
    await service.delete_item(db, ctx, item_id)


@router.post("/items/{item_id}/payments", response_model=BudgetOut, status_code=201)
async def add_payment(
    item_id: uuid.UUID,
    body: PaymentIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> BudgetOut:
    return await service.add_payment(db, ctx, item_id, body)


@router.patch("/items/{item_id}/payments/{payment_id}", response_model=BudgetOut)
async def update_payment(
    item_id: uuid.UUID,
    payment_id: uuid.UUID,
    body: PaymentUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> BudgetOut:
    return await service.update_payment(db, ctx, item_id, payment_id, body)


@router.delete("/items/{item_id}/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(
    item_id: uuid.UUID,
    payment_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.BUDGET_WRITE),
) -> None:
    await service.delete_payment(db, ctx, item_id, payment_id)
