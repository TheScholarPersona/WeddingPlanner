"""Clients, vendors, weddings (projects), team assignments, templates, milestones and tasks.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15

RLS overview (on top of tenant isolation):
- projects: org admins see all; others only weddings they created or are assigned to.
- milestones, tasks, project_vendors: only for weddings the user can access.
- clients: org admins, the creator, and teams of the client's weddings.
- client_contacts: follow their client.
- vendors, templates: team roles only (not client logins).
- project_members: tenant only (assignment metadata, needed to evaluate the rules above).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
ORG = "organization_id = app_current_org_id()"
TEAM = f"{ORG} AND app_current_role() IN ('org_admin', 'member')"
PROJECT_ACCESS = f"{ORG} AND app_can_access_project(project_id)"


def _id() -> sa.Column[object]:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True)


def _org() -> sa.Column[object]:
    return sa.Column(
        "organization_id",
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _fk(name: str, target: str, ondelete: str, nullable: bool = False) -> sa.Column[object]:
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False),
    ]


def _policy(table: str, using: str, check: str | None = None) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY access ON {table} USING ({using}) WITH CHECK ({check or using})")


def upgrade() -> None:
    op.create_table(
        "clients",
        _id(),
        _org(),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="inquiry"),
        sa.Column("source", sa.String(100)),
        sa.Column("notes_internal", sa.Text),
        _fk("created_by", "users.id", "SET NULL", nullable=True),
        *_timestamps(),
        sa.Column("deleted_at", TZ),
        sa.CheckConstraint(
            "status IN ('inquiry', 'proposal', 'booked', 'completed', 'lost')", name="status"
        ),
    )
    op.create_table(
        "client_contacts",
        _id(),
        _org(),
        _fk("client_id", "clients.id", "CASCADE"),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("role", sa.String(20), nullable=False, server_default="partner"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        _fk("user_id", "users.id", "SET NULL", nullable=True),
        *_timestamps(),
        sa.CheckConstraint("role IN ('partner', 'family', 'other')", name="role"),
    )
    op.create_index("ix_client_contacts_client_id", "client_contacts", ["client_id"])

    op.create_table(
        "vendors",
        _id(),
        _org(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("contact_name", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(50)),
        sa.Column("website", sa.String(300)),
        sa.Column("notes_internal", sa.Text),
        sa.Column("rating", sa.SmallInteger),
        *_timestamps(),
        sa.Column("deleted_at", TZ),
        sa.CheckConstraint(
            "category IN ('venue', 'catering', 'photo', 'video', 'flowers', 'music', 'decor', "
            "'attire', 'stationery', 'other')",
            name="category",
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating"),
    )

    op.create_table(
        "projects",
        _id(),
        _org(),
        _fk("client_id", "clients.id", "RESTRICT"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("wedding_date", sa.Date),
        sa.Column("venue_name", sa.String(200)),
        sa.Column("venue_address", sa.String(500)),
        sa.Column("guest_count_planned", sa.Integer),
        sa.Column("style_notes", sa.Text),
        sa.Column("notes_internal", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="planning"),
        sa.Column("archived_at", TZ),
        _fk("created_by", "users.id", "SET NULL", nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_timestamps(),
        sa.Column("deleted_at", TZ),
        sa.CheckConstraint(
            "status IN ('planning', 'active', 'completed', 'archived')", name="status"
        ),
        sa.CheckConstraint("guest_count_planned >= 0", name="guest_count"),
    )
    op.create_index("ix_projects_client_id", "projects", ["client_id"])
    op.create_index("ix_projects_org_wedding_date", "projects", ["organization_id", "wedding_date"])

    op.create_table(
        "project_members",
        _id(),
        _org(),
        _fk("project_id", "projects.id", "CASCADE"),
        _fk("membership_id", "memberships.id", "CASCADE"),
        sa.Column("project_role", sa.String(20), nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "membership_id", name="uq_project_members_project_id"),
        sa.CheckConstraint(
            "project_role IN ('lead', 'planner', 'viewer', 'client')", name="project_role"
        ),
    )
    op.create_index("ix_project_members_project_id", "project_members", ["project_id"])
    op.create_index("ix_project_members_membership_id", "project_members", ["membership_id"])

    op.create_table(
        "project_vendors",
        _id(),
        _org(),
        _fk("project_id", "projects.id", "CASCADE"),
        _fk("vendor_id", "vendors.id", "CASCADE"),
        sa.Column("status", sa.String(20), nullable=False, server_default="considered"),
        sa.Column("notes", sa.Text),
        *_timestamps(),
        sa.UniqueConstraint("project_id", "vendor_id", name="uq_project_vendors_project_id"),
        sa.CheckConstraint(
            "status IN ('considered', 'requested', 'booked', 'cancelled')", name="status"
        ),
    )
    op.create_index("ix_project_vendors_project_id", "project_vendors", ["project_id"])

    op.create_table(
        "project_templates",
        _id(),
        _org(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        *_timestamps(),
    )
    op.create_table(
        "template_items",
        _id(),
        _org(),
        _fk("template_id", "project_templates.id", "CASCADE"),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("offset_days", sa.Integer, nullable=False),
        sa.Column("assignee_type", sa.String(10), nullable=False, server_default="team"),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        _fk("parent_item_id", "template_items.id", "CASCADE", nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('milestone', 'task')", name="kind"),
        sa.CheckConstraint("assignee_type IN ('team', 'client')", name="assignee_type"),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
    )
    op.create_index("ix_template_items_template_id", "template_items", ["template_id"])

    op.create_table(
        "milestones",
        _id(),
        _org(),
        _fk("project_id", "projects.id", "CASCADE"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column("completed_at", TZ),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        *_timestamps(),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
    )
    op.create_index("ix_milestones_project_id", "milestones", ["project_id"])

    op.create_table(
        "tasks",
        _id(),
        _org(),
        _fk("project_id", "projects.id", "CASCADE"),
        _fk("milestone_id", "milestones.id", "SET NULL", nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("due_date", sa.Date),
        _fk("assignee_membership_id", "memberships.id", "SET NULL", nullable=True),
        sa.Column("assignee_type", sa.String(10), nullable=False, server_default="team"),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("completed_at", TZ),
        _fk("completed_by", "users.id", "SET NULL", nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_timestamps(),
        sa.Column("deleted_at", TZ),
        sa.CheckConstraint("status IN ('open', 'in_progress', 'done', 'cancelled')", name="status"),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high')", name="priority"),
        sa.CheckConstraint("assignee_type IN ('team', 'client')", name="assignee_type"),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
    )
    op.create_index("ix_tasks_project_status_due", "tasks", ["project_id", "status", "due_date"])

    # --- Access functions --------------------------------------------------------------
    # SECURITY DEFINER so that policies can consult project_members without recursion.
    # It only ever answers for the current user in the current organization.
    op.execute(
        """
        CREATE FUNCTION app_is_project_member(p_project uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM project_members pm
                JOIN memberships m ON m.id = pm.membership_id
                WHERE pm.project_id = p_project
                  AND m.user_id = app_current_user_id()
                  AND m.organization_id = app_current_org_id()
                  AND m.status = 'active'
            )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_is_project_member(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_is_project_member(uuid) TO app_user")
    op.execute(
        """
        CREATE FUNCTION app_can_access_project(p_project uuid) RETURNS boolean
        LANGUAGE sql STABLE
        AS $$ SELECT app_current_role() = 'org_admin' OR app_is_project_member(p_project) $$
        """
    )

    # --- Row-level security ----------------------------------------------------------------
    _policy(
        "projects",
        f"{ORG} AND (app_current_role() = 'org_admin' OR created_by = app_current_user_id() "
        "OR app_is_project_member(id))",
        check=ORG,
    )
    op.execute("ALTER TABLE project_members ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY access ON project_members USING ({ORG}) WITH CHECK ({ORG})")
    for table in ("project_vendors", "milestones", "tasks"):
        _policy(table, PROJECT_ACCESS)
    _policy(
        "clients",
        f"{ORG} AND (app_current_role() = 'org_admin' OR created_by = app_current_user_id() "
        "OR EXISTS (SELECT 1 FROM projects p WHERE p.client_id = clients.id))",
        check=ORG,
    )
    _policy(
        "client_contacts",
        f"{ORG} AND EXISTS (SELECT 1 FROM clients c WHERE c.id = client_contacts.client_id)",
        check=ORG,
    )
    for table in ("vendors", "project_templates", "template_items"):
        _policy(table, TEAM)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS access ON client_contacts")
    op.execute("DROP POLICY IF EXISTS access ON clients")
    for table in (
        "tasks",
        "milestones",
        "template_items",
        "project_templates",
        "project_vendors",
        "project_members",
        "projects",
        "vendors",
        "client_contacts",
        "clients",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS app_can_access_project(uuid)")
    op.execute("DROP FUNCTION IF EXISTS app_is_project_member(uuid)")
