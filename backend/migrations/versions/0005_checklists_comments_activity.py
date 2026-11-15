"""Task checklists, comments and the activity feed.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-15

RLS: checklist items follow their task; comments and activity events require access to the
wedding (app_can_access_project), exactly like tasks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
ORG = "organization_id = app_current_org_id()"


def _org() -> sa.Column[object]:
    return sa.Column(
        "organization_id",
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _project() -> sa.Column[object]:
    return sa.Column(
        "project_id",
        UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _policy(table: str, using: str, check: str | None = None) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY access ON {table} USING ({using}) WITH CHECK ({check or using})")


def upgrade() -> None:
    op.create_table(
        "task_checklist_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("is_done", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org(),
        _project(),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "author_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("edited_at", TZ),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target_type IN ('project', 'task', 'milestone')", name="target_type"),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 5000", name="body_length"),
    )
    op.create_index("ix_comments_target", "comments", ["target_type", "target_id"])
    op.create_table(
        "activity_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org(),
        _project(),
        sa.Column(
            "actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("verb", sa.String(40), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True)),
        sa.Column("summary", sa.String(300), nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
    )
    op.create_index(
        "ix_activity_events_project_created",
        "activity_events",
        ["project_id", sa.text("created_at DESC")],
    )

    _policy(
        "task_checklist_items",
        f"{ORG} AND EXISTS (SELECT 1 FROM tasks t WHERE t.id = task_checklist_items.task_id)",
    )
    for table in ("comments", "activity_events"):
        _policy(table, f"{ORG} AND app_can_access_project(project_id)")


def downgrade() -> None:
    op.drop_table("activity_events")
    op.drop_table("comments")
    op.drop_table("task_checklist_items")
