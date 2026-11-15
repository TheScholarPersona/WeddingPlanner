"""Give every existing organization the default wedding template.

Organizations created before Sprint 2 have no templates; new ones get it on creation.
Runs per organization inside its tenant context, so it also works where RLS is forced
for the schema owner.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.ids import uuid7
from app.templates.service import DEFAULT_TEMPLATE

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INSERT_TEMPLATE = sa.text(
    "INSERT INTO project_templates (id, organization_id, name, description, is_default) "
    "VALUES (:id, :org, :name, :description, true)"
)
INSERT_ITEM = sa.text(
    "INSERT INTO template_items (id, organization_id, template_id, kind, title, offset_days, "
    "assignee_type, visibility, parent_item_id, position) "
    "VALUES (:id, :org, :template, :kind, :title, :offset, :assignee, :visibility, :parent, :pos)"
)


def upgrade() -> None:
    bind = op.get_bind()
    orgs = bind.execute(
        sa.text(
            "SELECT o.id FROM organizations o WHERE NOT EXISTS "
            "(SELECT 1 FROM project_templates t WHERE t.organization_id = o.id)"
        )
    ).scalars()
    for org in list(orgs):
        bind.execute(
            sa.text(
                "SELECT set_config('app.org_id', :org, true), "
                "set_config('app.role', 'org_admin', true)"
            ),
            {"org": str(org)},
        )
        template = uuid7()
        bind.execute(
            INSERT_TEMPLATE,
            {
                "id": template,
                "org": org,
                "name": "Standard wedding (12 months)",
                "description": "Milestones and tasks for a wedding planned about a year ahead.",
            },
        )
        position = 0
        for title, offset, visible, tasks in DEFAULT_TEMPLATE:
            milestone = uuid7()
            bind.execute(
                INSERT_ITEM,
                {
                    "id": milestone,
                    "org": org,
                    "template": template,
                    "kind": "milestone",
                    "title": title,
                    "offset": offset,
                    "assignee": "team",
                    "visibility": "client" if visible else "internal",
                    "parent": None,
                    "pos": position,
                },
            )
            position += 1
            for task_title, task_offset, assignee, task_visible in tasks:
                bind.execute(
                    INSERT_ITEM,
                    {
                        "id": uuid7(),
                        "org": org,
                        "template": template,
                        "kind": "task",
                        "title": task_title,
                        "offset": task_offset,
                        "assignee": assignee,
                        "visibility": "client" if task_visible else "internal",
                        "parent": milestone,
                        "pos": position,
                    },
                )
                position += 1


def downgrade() -> None:
    # Templates are user data from here on; nothing to undo safely.
    pass
