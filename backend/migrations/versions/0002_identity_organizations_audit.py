"""Identity, organizations, memberships, invitations and the audit log.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15

RLS overview:
- users, sessions, password_reset_tokens: global identity data without organization_id. Not
  tenant data; only the auth service touches them.
- organizations: visible inside its own tenant context and to its active members.
- memberships: tenant-isolated; a user may also read their own memberships (needed for /me).
- invitations: tenant-isolated; token lookup before login goes through the SECURITY DEFINER
  function app_invitation_by_token(), so the table is not FORCEd.
- audit_log: tenant-isolated reads; inserts for the own tenant or without tenant; no UPDATE or
  DELETE for the runtime role.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.rls import disable_tenant_rls, enable_tenant_rls

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False, server_default="en"),
        sa.Column("email_verified_at", TZ),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", TZ),
        sa.Column("last_login_at", TZ),
        *_timestamps(),
        sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
    )
    op.create_index("uq_users_email", "users", ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("reauth_at", TZ),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("used_at", TZ),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("accent_color", sa.String(7)),
        sa.Column("locale", sa.String(10), nullable=False, server_default="de-DE"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Berlin"),
        sa.Column(
            "client_access_days_after_archive", sa.Integer, nullable=False, server_default="90"
        ),
        *_timestamps(),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="status"),
        sa.CheckConstraint("accent_color ~ '^#[0-9A-Fa-f]{6}$'", name="accent_color"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("invited_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_organization_id"),
        sa.CheckConstraint("role IN ('org_admin', 'member', 'client')", name="role"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="status"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("accepted_at", TZ),
        sa.Column("revoked_at", TZ),
        sa.CheckConstraint("role IN ('org_admin', 'member', 'client')", name="role"),
        sa.CheckConstraint("email = lower(email)", name="email_lowercase"),
    )
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "actor_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True)),
        sa.Column("changes", JSONB),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_audit_log_org_created", "audit_log", ["organization_id", sa.text("created_at DESC")]
    )

    # --- Row-level security -------------------------------------------------------------
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organization_read ON organizations FOR SELECT
        USING (
            id = app_current_org_id()
            OR id IN (
                SELECT organization_id FROM memberships
                WHERE user_id = app_current_user_id() AND status = 'active'
            )
        )
        """
    )
    op.execute(
        "CREATE POLICY organization_write ON organizations FOR INSERT "
        "WITH CHECK (id = app_current_org_id())"
    )
    op.execute(
        "CREATE POLICY organization_update ON organizations FOR UPDATE "
        "USING (id = app_current_org_id()) WITH CHECK (id = app_current_org_id())"
    )

    for statement in enable_tenant_rls("memberships"):
        op.execute(statement)
    op.execute(
        "CREATE POLICY own_memberships ON memberships FOR SELECT "
        "USING (user_id = app_current_user_id())"
    )

    for statement in enable_tenant_rls("invitations", force=False):
        op.execute(statement)

    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY audit_read ON audit_log FOR SELECT "
        "USING (organization_id = app_current_org_id())"
    )
    op.execute(
        "CREATE POLICY audit_insert ON audit_log FOR INSERT "
        "WITH CHECK (organization_id IS NULL OR organization_id = app_current_org_id())"
    )
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM app_user")

    # Invitation lookup by token before the tenant is known (accept-invitation page).
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


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_invitation_by_token(text)")
    op.execute("DROP POLICY IF EXISTS organization_read ON organizations")
    for statement in disable_tenant_rls("invitations"):
        op.execute(statement)
    op.drop_table("audit_log")
    op.drop_table("invitations")
    op.drop_table("memberships")
    op.drop_table("organizations")
    op.drop_table("password_reset_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
