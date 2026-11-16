"""Moodboards: boards, sections, images and hearts per wedding.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-16

- Wedding-access RLS like tasks (app_can_access_project).
- Couples (app.role = 'client') only see boards shared with them (visibility = 'client') and
  what belongs to those boards. Comments on images of other boards stay hidden from them too.
- comments.target_type gains 'moodboard_item'.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
ORG = "organization_id = app_current_org_id()"
PROJECT_ACCESS = f"{ORG} AND app_can_access_project(project_id)"
NOT_CLIENT = "app_current_role() IS DISTINCT FROM 'client'"
VISIBLE_BOARD = "EXISTS (SELECT 1 FROM moodboards b WHERE b.id = board_id)"


def _common(name: str, *columns: sa.Column[object], timestamps: bool = True) -> None:
    op.create_table(
        name,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        *columns,
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        *(
            [sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False)]
            if timestamps
            else []
        ),
    )
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY access ON {name} USING ({PROJECT_ACCESS}) WITH CHECK ({PROJECT_ACCESS})"
    )


def _restrict(table: str, condition: str) -> None:
    op.execute(f"CREATE POLICY client_scope ON {table} AS RESTRICTIVE USING ({condition})")


def _board_fk() -> sa.Column[object]:
    return sa.Column(
        "board_id",
        UUID(as_uuid=True),
        sa.ForeignKey("moodboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _user(name: str) -> sa.Column[object]:
    return sa.Column(name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"))


def upgrade() -> None:
    _common(
        "moodboards",
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("created_by_type", sa.String(10), nullable=False, server_default="team"),
        _user("created_by"),
        sa.Column("palette", JSONB, nullable=False, server_default="[]"),
        sa.Column("notes_internal", sa.Text),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
        sa.CheckConstraint("created_by_type IN ('team', 'client')", name="created_by_type"),
    )
    _common(
        "moodboard_sections",
        _board_fk(),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    _common(
        "moodboard_items",
        _board_fk(),
        sa.Column(
            "section_id",
            UUID(as_uuid=True),
            sa.ForeignKey("moodboard_sections.id", ondelete="SET NULL"),
        ),
        sa.Column("caption", sa.String(300)),
        sa.Column("status", sa.String(10), nullable=False, server_default="proposed"),
        sa.Column("storage_key", sa.String(300), nullable=False, unique=True),
        sa.Column("thumb_key", sa.String(300)),
        sa.Column("display_key", sa.String(300)),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("scan_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("processed_at", TZ),
        _user("uploaded_by"),
        sa.Column("uploaded_by_type", sa.String(10), nullable=False, server_default="team"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint("status IN ('proposed', 'selected', 'discarded')", name="status"),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'failed', 'not_scanned')",
            name="scan_status",
        ),
        sa.CheckConstraint("uploaded_by_type IN ('team', 'client')", name="uploaded_by_type"),
    )
    _common(
        "moodboard_reactions",
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("moodboard_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("item_id", "user_id", name="uq_moodboard_reactions_user"),
        timestamps=False,
    )

    # Couples: only boards shared with them, and what belongs to those boards.
    _restrict("moodboards", f"{NOT_CLIENT} OR visibility = 'client'")
    _restrict("moodboard_sections", f"{NOT_CLIENT} OR {VISIBLE_BOARD}")
    _restrict("moodboard_items", f"{NOT_CLIENT} OR {VISIBLE_BOARD}")
    _restrict(
        "moodboard_reactions",
        f"{NOT_CLIENT} OR EXISTS (SELECT 1 FROM moodboard_items i WHERE i.id = item_id)",
    )

    # Comments on images: new target type; a couple never sees comments on images of boards
    # that are not shared with them, even if such a comment is marked visible.
    op.drop_constraint("target_type", "comments", type_="check")
    op.create_check_constraint(
        "target_type",
        "comments",
        "target_type IN ('project', 'task', 'milestone', 'moodboard_item')",
    )
    op.execute(
        "CREATE POLICY moodboard_scope ON comments AS RESTRICTIVE USING ("
        f"{NOT_CLIENT} OR target_type <> 'moodboard_item' "
        "OR EXISTS (SELECT 1 FROM moodboard_items i WHERE i.id = target_id))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY moodboard_scope ON comments")
    op.execute("DELETE FROM comments WHERE target_type = 'moodboard_item'")
    op.drop_constraint("target_type", "comments", type_="check")
    op.create_check_constraint(
        "target_type", "comments", "target_type IN ('project', 'task', 'milestone')"
    )
    for table in ("moodboard_reactions", "moodboard_items", "moodboard_sections", "moodboards"):
        op.drop_table(table)
