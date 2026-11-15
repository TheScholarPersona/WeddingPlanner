"""Budgets and client (couple) access.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-15

- budgets, budget_categories, budget_items, payments: wedding-access RLS like tasks.
- invitations.project_id for couple invitations; the token lookup function returns it.
- Client logins (app.role = 'client') get RESTRICTIVE policies on top of the existing ones:
  they only see rows shared with the couple (visibility = 'client') and never team-only
  data such as invitations, the audit log, other memberships or vendor links.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
ORG = "organization_id = app_current_org_id()"
PROJECT_ACCESS = f"{ORG} AND app_can_access_project(project_id)"
NOT_CLIENT = "app_current_role() IS DISTINCT FROM 'client'"
SHARED = f"{NOT_CLIENT} OR visibility = 'client'"


def _base(name: str, *columns: sa.Column[object]) -> None:
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
            index=name != "budgets",
            unique=name == "budgets",
        ),
        *columns,
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False),
    )
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY access ON {name} USING ({PROJECT_ACCESS})")


def _restrict(table: str, condition: str, name: str = "client_scope") -> None:
    op.execute(f"CREATE POLICY {name} ON {table} AS RESTRICTIVE USING ({condition})")


def upgrade() -> None:
    _base(
        "budgets",
        sa.Column("total_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("warning_threshold_pct", sa.Integer, nullable=False, server_default="90"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    _base(
        "budget_categories",
        sa.Column(
            "budget_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    _base(
        "budget_items",
        sa.Column(
            "category_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budget_categories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "vendor_id", UUID(as_uuid=True), sa.ForeignKey("vendors.id", ondelete="SET NULL")
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("planned_cents", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("quoted_cents", sa.BigInteger),
        sa.Column("contracted_cents", sa.BigInteger),
        sa.Column("internal_cost_cents", sa.BigInteger),
        sa.Column("paid_by", sa.String(10), nullable=False, server_default="client"),
        sa.Column("notes_internal", sa.Text),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint("paid_by IN ('client', 'planner')", name="paid_by"),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
        sa.CheckConstraint(
            "planned_cents >= 0 AND coalesce(quoted_cents, 0) >= 0 "
            "AND coalesce(contracted_cents, 0) >= 0 AND coalesce(internal_cost_cents, 0) >= 0",
            name="amounts",
        ),
    )
    _base(
        "payments",
        sa.Column(
            "budget_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("budget_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("amount_cents", sa.BigInteger, nullable=False),
        sa.Column("due_date", sa.Date),
        sa.Column("paid_at", TZ),
        sa.CheckConstraint("amount_cents > 0", name="amount"),
    )

    # Couples see only shared budget items and their payments.
    _restrict("budget_items", SHARED)
    _restrict(
        "payments",
        f"{NOT_CLIENT} OR EXISTS (SELECT 1 FROM budget_items b WHERE b.id = budget_item_id)",
    )

    # Couple invitations point at a wedding.
    op.add_column(
        "invitations",
        sa.Column(
            "project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE")
        ),
    )
    op.execute("DROP FUNCTION app_invitation_by_token(text)")
    op.execute(
        """
        CREATE FUNCTION app_invitation_by_token(p_token_hash text)
        RETURNS TABLE (
            id uuid, organization_id uuid, organization_name text, email text, role text,
            expires_at timestamptz, accepted_at timestamptz, revoked_at timestamptz,
            project_id uuid
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
            SELECT i.id, i.organization_id, o.name, i.email, i.role,
                   i.expires_at, i.accepted_at, i.revoked_at, i.project_id
            FROM invitations i JOIN organizations o ON o.id = i.organization_id
            WHERE i.token_hash = p_token_hash AND o.status = 'active'
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_invitation_by_token(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_invitation_by_token(text) TO app_user")

    # Client logins: only what is shared with the couple.
    for table in ("tasks", "milestones", "comments", "activity_events"):
        _restrict(table, SHARED)
    for table in ("project_vendors", "invitations", "audit_log"):
        _restrict(table, NOT_CLIENT)
    _restrict("project_members", f"{NOT_CLIENT} OR app_is_project_member(project_id)")
    # app_is_project_member() (SECURITY DEFINER, schema owner) reads memberships; the policy
    # below calls it, so the owner must not be subject to memberships' own policies or the
    # check would recurse. The application never connects as the owner.
    op.execute("ALTER TABLE memberships NO FORCE ROW LEVEL SECURITY")
    _restrict(
        "memberships",
        f"{NOT_CLIENT} OR user_id = app_current_user_id() OR id IN ("
        "SELECT pm.membership_id FROM project_members pm "
        "WHERE app_is_project_member(pm.project_id))",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE memberships FORCE ROW LEVEL SECURITY")
    for table in (
        "memberships",
        "project_members",
        "audit_log",
        "invitations",
        "project_vendors",
        "activity_events",
        "comments",
        "milestones",
        "tasks",
    ):
        op.execute(f"DROP POLICY IF EXISTS client_scope ON {table}")
    op.execute("DROP FUNCTION app_invitation_by_token(text)")
    op.execute(
        """
        CREATE FUNCTION app_invitation_by_token(p_token_hash text)
        RETURNS TABLE (
            id uuid, organization_id uuid, organization_name text, email text, role text,
            expires_at timestamptz, accepted_at timestamptz, revoked_at timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
            SELECT i.id, i.organization_id, o.name, i.email, i.role,
                   i.expires_at, i.accepted_at, i.revoked_at
            FROM invitations i JOIN organizations o ON o.id = i.organization_id
            WHERE i.token_hash = p_token_hash AND o.status = 'active'
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app_invitation_by_token(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_invitation_by_token(text) TO app_user")
    op.drop_column("invitations", "project_id")
    for table in ("payments", "budget_items", "budget_categories", "budgets"):
        op.drop_table(table)
