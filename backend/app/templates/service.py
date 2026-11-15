"""Project templates: milestones and tasks with due dates relative to the wedding date."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.authz.deps import OrgContext, not_found
from app.core.errors import ProblemError
from app.tasks.models import Milestone, Task
from app.templates.models import ProjectTemplate, TemplateItem, TemplateItemKind
from app.templates.schemas import (
    TemplateDetailOut,
    TemplateIn,
    TemplateItemIn,
    TemplateItemOut,
    TemplateItemUpdateIn,
    TemplateOut,
    TemplateUpdateIn,
)

# (milestone, offset_days, client-visible, [(task, offset_days, assignee, client-visible)])
DEFAULT_TEMPLATE: list[tuple[str, int, bool, list[tuple[str, int, str, bool]]]] = [
    (
        "Venue and date secured",
        -360,
        True,
        [
            ("Agree on the overall budget", -380, "client", True),
            ("Shortlist venues", -375, "team", False),
            ("Visit venues together", -368, "team", True),
            ("Sign the venue contract", -360, "client", True),
        ],
    ),
    (
        "Key vendors booked",
        -270,
        True,
        [
            ("Book photographer", -300, "team", True),
            ("Book caterer", -290, "team", True),
            ("Book music", -280, "team", True),
            ("Collect vendor contracts", -270, "team", False),
        ],
    ),
    (
        "Invitations sent",
        -150,
        True,
        [
            ("Finalise guest list", -195, "client", True),
            ("Choose wedding invitations", -185, "client", True),
            ("Order printed invitations", -175, "team", False),
            ("Set up wedding website", -170, "client", True),
        ],
    ),
    (
        "Menu and décor final",
        -75,
        True,
        [
            ("Menu tasting", -110, "team", True),
            ("Choose table flowers", -100, "client", True),
            ("Decide on wedding cake design", -90, "client", True),
            ("Confirm décor rental", -80, "team", False),
        ],
    ),
    (
        "Day-of timeline approved",
        -30,
        True,
        [
            ("Draft day-of timeline", -45, "team", True),
            ("Share timeline with vendors", -35, "team", False),
            ("Final vendor confirmations", -14, "team", False),
        ],
    ),
    ("Wedding day", 0, True, []),
]


async def create_default_template(db: AsyncSession, organization_id: uuid.UUID) -> ProjectTemplate:
    template = ProjectTemplate(
        organization_id=organization_id,
        name="Standard wedding (12 months)",
        description="Milestones and tasks for a wedding planned about a year ahead.",
        is_default=True,
    )
    db.add(template)
    await db.flush()
    position = 0
    for title, offset, visible, tasks in DEFAULT_TEMPLATE:
        milestone = TemplateItem(
            organization_id=organization_id,
            template_id=template.id,
            kind=TemplateItemKind.MILESTONE,
            title=title,
            offset_days=offset,
            visibility="client" if visible else "internal",
            position=position,
        )
        db.add(milestone)
        await db.flush()
        position += 1
        for task_title, task_offset, assignee, task_visible in tasks:
            db.add(
                TemplateItem(
                    organization_id=organization_id,
                    template_id=template.id,
                    kind=TemplateItemKind.TASK,
                    title=task_title,
                    offset_days=task_offset,
                    assignee_type=assignee,
                    visibility="client" if task_visible else "internal",
                    parent_item_id=milestone.id,
                    position=position,
                )
            )
            position += 1
    await db.flush()
    return template


async def _get(db: AsyncSession, template_id: uuid.UUID) -> ProjectTemplate:
    template = await db.get(ProjectTemplate, template_id)
    if template is None:
        raise not_found()
    return template


async def _items(db: AsyncSession, template_id: uuid.UUID) -> list[TemplateItem]:
    return list(
        (
            await db.execute(
                select(TemplateItem)
                .where(TemplateItem.template_id == template_id)
                .order_by(TemplateItem.position, TemplateItem.offset_days)
            )
        ).scalars()
    )


def _item_out(item: TemplateItem) -> TemplateItemOut:
    return TemplateItemOut.model_validate(item, from_attributes=True)


async def list_templates(db: AsyncSession) -> list[TemplateOut]:
    counts = (
        select(
            TemplateItem.template_id,
            func.count().filter(TemplateItem.kind == "milestone").label("milestones"),
            func.count().filter(TemplateItem.kind == "task").label("tasks"),
        )
        .group_by(TemplateItem.template_id)
        .subquery()
    )
    rows = await db.execute(
        select(ProjectTemplate, counts.c.milestones, counts.c.tasks)
        .outerjoin(counts, counts.c.template_id == ProjectTemplate.id)
        .order_by(ProjectTemplate.is_default.desc(), ProjectTemplate.name)
    )
    return [
        TemplateOut(
            id=t.id,
            name=t.name,
            description=t.description,
            is_default=t.is_default,
            milestone_count=m or 0,
            task_count=n or 0,
        )
        for t, m, n in rows.all()
    ]


async def get_template(db: AsyncSession, template_id: uuid.UUID) -> TemplateDetailOut:
    template = await _get(db, template_id)
    items = await _items(db, template_id)
    return TemplateDetailOut(
        id=template.id,
        name=template.name,
        description=template.description,
        is_default=template.is_default,
        milestone_count=sum(i.kind == "milestone" for i in items),
        task_count=sum(i.kind == "task" for i in items),
        items=[_item_out(i) for i in items],
    )


async def create_template(db: AsyncSession, ctx: OrgContext, body: TemplateIn) -> TemplateDetailOut:
    template = ProjectTemplate(
        organization_id=ctx.organization_id, name=body.name, description=body.description
    )
    db.add(template)
    await db.flush()
    if body.copy_from:
        source = await _items(db, (await _get(db, body.copy_from)).id)
        new_ids: dict[uuid.UUID, uuid.UUID] = {}
        for item in sorted(source, key=lambda i: i.parent_item_id is not None):
            copy = TemplateItem(
                organization_id=ctx.organization_id,
                template_id=template.id,
                kind=item.kind,
                title=item.title,
                description=item.description,
                offset_days=item.offset_days,
                assignee_type=item.assignee_type,
                visibility=item.visibility,
                parent_item_id=new_ids.get(item.parent_item_id) if item.parent_item_id else None,
                position=item.position,
            )
            db.add(copy)
            await db.flush()
            new_ids[item.id] = copy.id
    await audit.record(
        db,
        action="template.created",
        resource_type="template",
        resource_id=template.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return await get_template(db, template.id)


async def update_template(
    db: AsyncSession, ctx: OrgContext, template_id: uuid.UUID, body: TemplateUpdateIn
) -> TemplateDetailOut:
    template = await _get(db, template_id)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("is_default"):
        await db.execute(update(ProjectTemplate).values(is_default=False))
    for key, value in fields.items():
        if value is not None:
            setattr(template, key, value)
    await audit.record(
        db,
        action="template.updated",
        resource_type="template",
        resource_id=template.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    await db.flush()
    return await get_template(db, template.id)


async def delete_template(db: AsyncSession, ctx: OrgContext, template_id: uuid.UUID) -> None:
    template = await _get(db, template_id)
    await db.delete(template)
    await audit.record(
        db,
        action="template.deleted",
        resource_type="template",
        resource_id=template_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


async def _check_parent(db: AsyncSession, template_id: uuid.UUID, parent: uuid.UUID | None) -> None:
    if parent is None:
        return
    item = await db.get(TemplateItem, parent)
    if item is None or item.template_id != template_id or item.kind != "milestone":
        raise ProblemError(
            422, "invalid_parent", "Invalid milestone", "Tasks can only belong to a milestone."
        )


async def add_item(
    db: AsyncSession, ctx: OrgContext, template_id: uuid.UUID, body: TemplateItemIn
) -> TemplateItemOut:
    await _get(db, template_id)
    await _check_parent(db, template_id, body.parent_item_id if body.kind == "task" else None)
    item = TemplateItem(
        organization_id=ctx.organization_id,
        template_id=template_id,
        **body.model_dump(exclude={"parent_item_id"}),
        parent_item_id=body.parent_item_id if body.kind == "task" else None,
    )
    db.add(item)
    await db.flush()
    return _item_out(item)


async def update_item(
    db: AsyncSession, template_id: uuid.UUID, item_id: uuid.UUID, body: TemplateItemUpdateIn
) -> TemplateItemOut:
    item = await db.get(TemplateItem, item_id)
    if item is None or item.template_id != template_id:
        raise not_found()
    fields = body.model_dump(exclude_unset=True)
    if "parent_item_id" in fields and item.kind == "task":
        await _check_parent(db, template_id, fields["parent_item_id"])
    for key, value in fields.items():
        if value is not None or key == "parent_item_id":
            setattr(item, key, value)
    await db.flush()
    return _item_out(item)


async def delete_item(db: AsyncSession, template_id: uuid.UUID, item_id: uuid.UUID) -> None:
    item = await db.get(TemplateItem, item_id)
    if item is None or item.template_id != template_id:
        raise not_found()
    await db.delete(item)


async def apply_template(
    db: AsyncSession,
    *,
    template_id: uuid.UUID,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    wedding_date: date | None,
) -> int:
    """Create milestones and tasks for a project; returns the number of tasks created."""
    await _get(db, template_id)
    items = await _items(db, template_id)

    def due(offset: int) -> date | None:
        return wedding_date + timedelta(days=offset) if wedding_date else None

    milestone_ids: dict[uuid.UUID, uuid.UUID] = {}
    for item in items:
        if item.kind == "milestone":
            milestone = Milestone(
                organization_id=organization_id,
                project_id=project_id,
                title=item.title,
                due_date=due(item.offset_days),
                position=item.position,
                visibility=item.visibility,
            )
            db.add(milestone)
            await db.flush()
            milestone_ids[item.id] = milestone.id
    count = 0
    for item in items:
        if item.kind == "task":
            db.add(
                Task(
                    organization_id=organization_id,
                    project_id=project_id,
                    milestone_id=milestone_ids.get(item.parent_item_id)
                    if item.parent_item_id
                    else None,
                    title=item.title,
                    description=item.description,
                    due_date=due(item.offset_days),
                    assignee_type=item.assignee_type,
                    visibility=item.visibility,
                    position=item.position,
                )
            )
            count += 1
    await db.flush()
    return count
