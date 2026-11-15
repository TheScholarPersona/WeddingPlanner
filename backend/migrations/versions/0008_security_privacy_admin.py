"""Two-factor authentication, consents, support access, platform administration, retention.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-15

- users: encrypted TOTP secret, deletion marker; recovery_codes (global, like sessions).
- sessions.mfa_pending: a password-only session that still needs the second factor.
- organizations.require_2fa: team members must use two-factor authentication.
- consents: optional permissions a couple gives (or withdraws) per organization.
- support_access_grants: time-limited permission for platform support to look into an
  organization (read-only). Not forced: the admin API checks grants before a tenant is set.
- SECURITY DEFINER functions for the platform admin overview and for retention cleanup.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
ORG = "organization_id = app_current_org_id()"
NOT_CLIENT = "app_current_role() IS DISTINCT FROM 'client'"
OWN = "user_id = app_current_user_id()"


def _definer(signature: str, body: str) -> None:
    op.execute(body)
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_user")


def _org_fk() -> sa.Column[object]:
    return sa.Column(
        "organization_id",
        UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def upgrade() -> None:
    # --- Two-factor authentication ---------------------------------------------------------
    op.add_column("users", sa.Column("totp_secret_enc", sa.Text))
    op.add_column("users", sa.Column("totp_enabled_at", TZ))
    op.add_column("users", sa.Column("deleted_at", TZ))
    op.add_column(
        "sessions",
        sa.Column("mfa_pending", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sessions", sa.Column("mfa_failures", sa.Integer, nullable=False, server_default="0")
    )
    op.add_column(
        "organizations",
        sa.Column("require_2fa", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "recovery_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("used_at", TZ),
    )

    # --- Consents --------------------------------------------------------------------------
    op.create_table(
        "consents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False),
        sa.Column("text_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("decided_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", "kind", name="uq_consents_kind"),
        sa.CheckConstraint("kind IN ('portfolio', 'reviews')", name="kind"),
    )
    op.execute("ALTER TABLE consents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE consents FORCE ROW LEVEL SECURITY")
    # The team reads consents of its clients; each person writes only their own.
    op.execute(
        f"CREATE POLICY read ON consents FOR SELECT USING ({ORG} AND ({OWN} OR {NOT_CLIENT}))"
    )
    op.execute(
        f"CREATE POLICY own_write ON consents USING ({ORG} AND {OWN}) WITH CHECK ({ORG} AND {OWN})"
    )

    # --- Support access --------------------------------------------------------------------
    op.create_table(
        "support_access_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column(
            "granted_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("reason", sa.String(300)),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ),
    )
    op.execute("ALTER TABLE support_access_grants ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY access ON support_access_grants USING ({ORG} AND {NOT_CLIENT}) WITH CHECK ({ORG})"
    )

    # --- Platform administration -----------------------------------------------------------
    # Only names and member counts cross tenant boundaries; content (weddings, clients'
    # data) stays behind forced RLS, which also applies to this function's owner.
    _definer(
        "app_admin_organizations()",
        """
        CREATE FUNCTION app_admin_organizations()
        RETURNS TABLE (
            id uuid, name text, slug text, status text, created_at timestamptz,
            require_2fa boolean, members bigint, clients bigint,
            support_until timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
            SELECT o.id, o.name, o.slug, o.status, o.created_at, o.require_2fa,
                (SELECT count(*) FROM memberships m
                  WHERE m.organization_id = o.id AND m.status = 'active' AND m.role <> 'client'),
                (SELECT count(*) FROM memberships m
                  WHERE m.organization_id = o.id AND m.status = 'active' AND m.role = 'client'),
                (SELECT max(g.expires_at) FROM support_access_grants g
                  WHERE g.organization_id = o.id AND g.revoked_at IS NULL
                    AND g.expires_at > now())
            FROM organizations o ORDER BY o.created_at DESC
        $$
        """,
    )
    _definer(
        "app_admin_set_organization_status(uuid, text)",
        """
        CREATE FUNCTION app_admin_set_organization_status(p_org uuid, p_status text)
        RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
        BEGIN
            IF p_status NOT IN ('active', 'suspended') THEN
                RAISE EXCEPTION 'invalid status';
            END IF;
            UPDATE organizations SET status = p_status, updated_at = now() WHERE id = p_org;
            RETURN FOUND;
        END
        $$
        """,
    )

    # --- Retention -------------------------------------------------------------------------
    _definer(
        "app_purge_expired()",
        """
        CREATE FUNCTION app_purge_expired()
        RETURNS TABLE (item text, removed bigint)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
        DECLARE n bigint;
        BEGIN
            DELETE FROM sessions
             WHERE expires_at < now() - interval '30 days'
                OR revoked_at < now() - interval '30 days';
            GET DIAGNOSTICS n = ROW_COUNT; item := 'sessions'; removed := n; RETURN NEXT;

            DELETE FROM password_reset_tokens WHERE expires_at < now() - interval '7 days';
            GET DIAGNOSTICS n = ROW_COUNT; item := 'password_reset_tokens'; removed := n;
            RETURN NEXT;

            DELETE FROM invitations
             WHERE accepted_at IS NULL AND expires_at < now() - interval '90 days';
            GET DIAGNOSTICS n = ROW_COUNT; item := 'invitations'; removed := n; RETURN NEXT;

            DELETE FROM calendar_feeds WHERE revoked_at < now() - interval '90 days';
            GET DIAGNOSTICS n = ROW_COUNT; item := 'calendar_feeds'; removed := n; RETURN NEXT;

            DELETE FROM support_access_grants WHERE expires_at < now() - interval '365 days';
            GET DIAGNOSTICS n = ROW_COUNT; item := 'support_access_grants'; removed := n;
            RETURN NEXT;
        END
        $$
        """,
    )
    # notification_log is forced RLS; it is cleaned per organization by the job instead.


def downgrade() -> None:
    op.execute("DROP FUNCTION app_purge_expired()")
    op.execute("DROP FUNCTION app_admin_set_organization_status(uuid, text)")
    op.execute("DROP FUNCTION app_admin_organizations()")
    op.drop_table("support_access_grants")
    op.drop_table("consents")
    op.drop_table("recovery_codes")
    op.drop_column("organizations", "require_2fa")
    op.drop_column("sessions", "mfa_failures")
    op.drop_column("sessions", "mfa_pending")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "totp_enabled_at")
    op.drop_column("users", "totp_secret_enc")
