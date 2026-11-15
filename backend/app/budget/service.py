"""Wedding budget: categories, items, payments, totals and warnings.

Forecast per item = contracted amount, else quoted, else planned. Warnings compare the forecast
with the budget frame and flag quotes above plan and overdue payments.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.authz.deps import ProjectContext, not_found
from app.budget.models import DEFAULT_CATEGORIES, Budget, BudgetCategory, BudgetItem, Payment
from app.budget.schemas import (
    BudgetOut,
    BudgetUpdateIn,
    CategoryIn,
    CategoryOut,
    CategoryUpdateIn,
    ItemIn,
    ItemOut,
    ItemUpdateIn,
    PaymentIn,
    PaymentOut,
    PaymentUpdateIn,
    Totals,
    UpcomingPayment,
    Warning,
)
from app.core.errors import ProblemError
from app.core.versioning import check_version
from app.vendors.models import Vendor

AMOUNT_FIELDS = ("planned_cents", "quoted_cents", "contracted_cents", "internal_cost_cents")


def forecast(item: BudgetItem) -> int:
    if item.contracted_cents is not None:
        return item.contracted_cents
    if item.quoted_cents is not None:
        return item.quoted_cents
    return item.planned_cents


async def create_budget(
    db: AsyncSession, organization_id: uuid.UUID, project_id: uuid.UUID
) -> Budget:
    budget = Budget(organization_id=organization_id, project_id=project_id)
    db.add(budget)
    await db.flush()
    for position, name in enumerate(DEFAULT_CATEGORIES):
        db.add(
            BudgetCategory(
                organization_id=organization_id,
                project_id=project_id,
                budget_id=budget.id,
                name=name,
                position=position,
            )
        )
    await db.flush()
    return budget


async def _budget(db: AsyncSession, ctx: ProjectContext) -> Budget:
    budget = (
        await db.execute(select(Budget).where(Budget.project_id == ctx.project.id))
    ).scalar_one_or_none()
    if budget is None:  # weddings created before budgets existed
        budget = await create_budget(db, ctx.organization_id, ctx.project.id)
    return budget


async def load(db: AsyncSession, project_id: uuid.UUID, budget: Budget) -> BudgetOut:
    """Build the budget view from whatever rows are visible to the current user (RLS)."""
    categories = list(
        (
            await db.execute(
                select(BudgetCategory)
                .where(BudgetCategory.budget_id == budget.id)
                .order_by(BudgetCategory.position, BudgetCategory.name)
            )
        ).scalars()
    )
    item_rows = (
        await db.execute(
            select(BudgetItem, Vendor.name)
            .outerjoin(Vendor, Vendor.id == BudgetItem.vendor_id)
            .where(BudgetItem.project_id == project_id)
            .order_by(BudgetItem.position, BudgetItem.title)
        )
    ).all()
    payments = list(
        (
            await db.execute(
                select(Payment)
                .where(Payment.project_id == project_id)
                .order_by(Payment.due_date.asc().nulls_last(), Payment.created_at)
            )
        ).scalars()
    )
    by_item: dict[uuid.UUID, list[Payment]] = defaultdict(list)
    for payment in payments:
        by_item[payment.budget_item_id].append(payment)

    today = datetime.now(UTC).date()
    items_by_category: dict[uuid.UUID, list[ItemOut]] = defaultdict(list)
    item_titles: dict[uuid.UUID, str] = {}
    totals = dict.fromkeys(
        ("planned", "quoted", "contracted", "paid", "forecast", "internal_cost"), 0
    )
    warnings: list[Warning] = []
    for item, vendor_name in item_rows:
        item_payments = by_item.get(item.id, [])
        paid = sum(p.amount_cents for p in item_payments if p.paid_at)
        item_titles[item.id] = item.title
        items_by_category[item.category_id].append(
            ItemOut(
                id=item.id,
                category_id=item.category_id,
                title=item.title,
                vendor_id=item.vendor_id,
                vendor_name=vendor_name,
                planned_cents=item.planned_cents,
                quoted_cents=item.quoted_cents,
                contracted_cents=item.contracted_cents,
                internal_cost_cents=item.internal_cost_cents,
                paid_by=item.paid_by,
                notes_internal=item.notes_internal,
                visibility=item.visibility,
                version=item.version,
                paid_cents=paid,
                payments=[
                    PaymentOut(
                        id=p.id,
                        label=p.label,
                        amount_cents=p.amount_cents,
                        due_date=p.due_date,
                        paid_at=p.paid_at,
                    )
                    for p in item_payments
                ],
            )
        )
        totals["planned"] += item.planned_cents
        totals["quoted"] += item.quoted_cents or 0
        totals["contracted"] += item.contracted_cents or 0
        totals["internal_cost"] += item.internal_cost_cents or 0
        totals["paid"] += paid
        totals["forecast"] += forecast(item)
        if item.quoted_cents is not None and item.quoted_cents > item.planned_cents > 0:
            warnings.append(
                Warning(
                    code="quote_above_plan",
                    amount_cents=item.quoted_cents - item.planned_cents,
                    item_id=item.id,
                    title=item.title,
                )
            )

    if budget.total_cents > 0:
        if totals["forecast"] > budget.total_cents:
            warnings.insert(
                0,
                Warning(code="over_budget", amount_cents=totals["forecast"] - budget.total_cents),
            )
        elif totals["forecast"] * 100 >= budget.total_cents * budget.warning_threshold_pct:
            warnings.insert(
                0,
                Warning(code="near_budget", amount_cents=budget.total_cents - totals["forecast"]),
            )

    upcoming = [
        UpcomingPayment(
            id=p.id,
            item_id=p.budget_item_id,
            item_title=item_titles.get(p.budget_item_id, ""),
            label=p.label,
            amount_cents=p.amount_cents,
            due_date=p.due_date,
            overdue=bool(p.due_date and p.due_date < today),
        )
        for p in payments
        if p.paid_at is None
    ]
    for due in upcoming:
        if due.overdue:
            warnings.append(
                Warning(
                    code="payment_overdue",
                    amount_cents=due.amount_cents,
                    item_id=due.item_id,
                    title=f"{due.item_title}: {due.label}",
                )
            )

    return BudgetOut(
        id=budget.id,
        total_cents=budget.total_cents,
        currency=budget.currency,
        warning_threshold_pct=budget.warning_threshold_pct,
        version=budget.version,
        totals=Totals(
            planned_cents=totals["planned"],
            quoted_cents=totals["quoted"],
            contracted_cents=totals["contracted"],
            paid_cents=totals["paid"],
            forecast_cents=totals["forecast"],
            internal_cost_cents=totals["internal_cost"],
            unplanned_cents=max(budget.total_cents - totals["planned"], 0),
        ),
        warnings=warnings,
        categories=[
            CategoryOut(
                id=c.id,
                name=c.name,
                position=c.position,
                planned_cents=sum(i.planned_cents for i in items_by_category[c.id]),
                forecast_cents=sum(
                    i.contracted_cents
                    if i.contracted_cents is not None
                    else i.quoted_cents
                    if i.quoted_cents is not None
                    else i.planned_cents
                    for i in items_by_category[c.id]
                ),
                items=items_by_category[c.id],
            )
            for c in categories
        ],
        upcoming_payments=upcoming,
    )


async def get_budget(db: AsyncSession, ctx: ProjectContext) -> BudgetOut:
    return await load(db, ctx.project.id, await _budget(db, ctx))


async def update_budget(
    db: AsyncSession, ctx: ProjectContext, body: BudgetUpdateIn, if_match: str | None
) -> BudgetOut:
    budget = await _budget(db, ctx)
    check_version(budget.version, if_match, "budget")
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    before = {k: getattr(budget, k) for k in fields}
    for key, value in fields.items():
        setattr(budget, key, value)
    budget.version += 1
    if changes := audit.diff(before, {k: getattr(budget, k) for k in fields}):
        await audit.record(
            db,
            action="budget.updated",
            resource_type="budget",
            resource_id=budget.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes=changes,
        )
    await db.flush()
    return await load(db, ctx.project.id, budget)


# --- Categories -------------------------------------------------------------------------


async def _category(
    db: AsyncSession, ctx: ProjectContext, category_id: uuid.UUID
) -> BudgetCategory:
    category = await db.get(BudgetCategory, category_id)
    if category is None or category.project_id != ctx.project.id:
        raise not_found()
    return category


async def add_category(db: AsyncSession, ctx: ProjectContext, body: CategoryIn) -> BudgetOut:
    budget = await _budget(db, ctx)
    count = len((await load(db, ctx.project.id, budget)).categories)
    db.add(
        BudgetCategory(
            organization_id=ctx.organization_id,
            project_id=ctx.project.id,
            budget_id=budget.id,
            name=body.name.strip(),
            position=count,
        )
    )
    await db.flush()
    return await load(db, ctx.project.id, budget)


async def update_category(
    db: AsyncSession, ctx: ProjectContext, category_id: uuid.UUID, body: CategoryUpdateIn
) -> BudgetOut:
    category = await _category(db, ctx, category_id)
    for key, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(category, key, value)
    await db.flush()
    return await get_budget(db, ctx)


async def delete_category(db: AsyncSession, ctx: ProjectContext, category_id: uuid.UUID) -> None:
    category = await _category(db, ctx, category_id)
    has_items = (
        await db.execute(
            select(BudgetItem.id).where(BudgetItem.category_id == category.id).limit(1)
        )
    ).first()
    if has_items:
        raise ProblemError(
            409, "category_not_empty", "Category has items", "Move or delete its items first."
        )
    await db.delete(category)


# --- Items ------------------------------------------------------------------------------


async def _item(db: AsyncSession, ctx: ProjectContext, item_id: uuid.UUID) -> BudgetItem:
    item = await db.get(BudgetItem, item_id)
    if item is None or item.project_id != ctx.project.id:
        raise not_found()
    return item


async def _check_vendor(db: AsyncSession, vendor_id: uuid.UUID | None) -> None:
    if vendor_id is None:
        return
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None or vendor.deleted_at is not None:
        raise ProblemError(422, "invalid_vendor", "Vendor not found", "Choose another vendor.")


def _audit_amounts(before: dict[str, object], item: BudgetItem) -> dict[str, object]:
    after = {k: getattr(item, k) for k in (*AMOUNT_FIELDS, "visibility", "title")}
    return audit.diff({k: before.get(k) for k in after}, after)


async def add_item(db: AsyncSession, ctx: ProjectContext, body: ItemIn) -> BudgetOut:
    await _category(db, ctx, body.category_id)
    await _check_vendor(db, body.vendor_id)
    item = BudgetItem(
        organization_id=ctx.organization_id, project_id=ctx.project.id, **body.model_dump()
    )
    db.add(item)
    await db.flush()
    await audit.record(
        db,
        action="budget_item.created",
        resource_type="budget_item",
        resource_id=item.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes=_audit_amounts({}, item),
    )
    return await get_budget(db, ctx)


async def update_item(
    db: AsyncSession,
    ctx: ProjectContext,
    item_id: uuid.UUID,
    body: ItemUpdateIn,
    if_match: str | None,
) -> BudgetOut:
    item = await _item(db, ctx, item_id)
    check_version(item.version, if_match, "budget item")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("category_id"):
        await _category(db, ctx, fields["category_id"])
    if "vendor_id" in fields:
        await _check_vendor(db, fields["vendor_id"])
    before = {k: getattr(item, k) for k in (*AMOUNT_FIELDS, "visibility", "title")}
    nullable = {
        "vendor_id",
        "quoted_cents",
        "contracted_cents",
        "internal_cost_cents",
        "notes_internal",
    }
    for key, value in fields.items():
        if value is not None or key in nullable:
            setattr(item, key, value)
    item.version += 1
    await db.flush()
    if changes := _audit_amounts(before, item):
        await audit.record(
            db,
            action="budget_item.updated",
            resource_type="budget_item",
            resource_id=item.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes=changes,
        )
    return await get_budget(db, ctx)


async def delete_item(db: AsyncSession, ctx: ProjectContext, item_id: uuid.UUID) -> None:
    item = await _item(db, ctx, item_id)
    await db.delete(item)
    await audit.record(
        db,
        action="budget_item.deleted",
        resource_type="budget_item",
        resource_id=item_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"title": {"old": item.title}},
    )


# --- Payments ---------------------------------------------------------------------------


async def add_payment(
    db: AsyncSession, ctx: ProjectContext, item_id: uuid.UUID, body: PaymentIn
) -> BudgetOut:
    item = await _item(db, ctx, item_id)
    payment = Payment(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        budget_item_id=item.id,
        label=body.label.strip(),
        amount_cents=body.amount_cents,
        due_date=body.due_date,
        paid_at=datetime.now(UTC) if body.paid else None,
    )
    db.add(payment)
    await db.flush()
    await audit.record(
        db,
        action="payment.created",
        resource_type="payment",
        resource_id=payment.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"amount_cents": {"new": body.amount_cents}, "paid": {"new": body.paid}},
    )
    return await get_budget(db, ctx)


async def _payment(
    db: AsyncSession, ctx: ProjectContext, item_id: uuid.UUID, payment_id: uuid.UUID
) -> Payment:
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.project_id != ctx.project.id or payment.budget_item_id != item_id:
        raise not_found()
    return payment


async def update_payment(
    db: AsyncSession,
    ctx: ProjectContext,
    item_id: uuid.UUID,
    payment_id: uuid.UUID,
    body: PaymentUpdateIn,
) -> BudgetOut:
    payment = await _payment(db, ctx, item_id, payment_id)
    fields = body.model_dump(exclude_unset=True)
    before = {"amount_cents": payment.amount_cents, "paid": payment.paid_at is not None}
    if "paid" in fields and fields["paid"] is not None:
        payment.paid_at = (payment.paid_at or datetime.now(UTC)) if fields["paid"] else None
    for key in ("label", "amount_cents"):
        if fields.get(key) is not None:
            setattr(payment, key, fields[key])
    if "due_date" in fields:
        payment.due_date = fields["due_date"]
    after = {"amount_cents": payment.amount_cents, "paid": payment.paid_at is not None}
    if changes := audit.diff(before, after):
        await audit.record(
            db,
            action="payment.updated",
            resource_type="payment",
            resource_id=payment.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes=changes,
        )
    await db.flush()
    return await get_budget(db, ctx)


async def delete_payment(
    db: AsyncSession, ctx: ProjectContext, item_id: uuid.UUID, payment_id: uuid.UUID
) -> None:
    payment = await _payment(db, ctx, item_id, payment_id)
    await db.delete(payment)
    await audit.record(
        db,
        action="payment.deleted",
        resource_type="payment",
        resource_id=payment_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"amount_cents": {"old": payment.amount_cents}},
    )
