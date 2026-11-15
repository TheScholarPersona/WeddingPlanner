"""Documents, calendar events and feeds, notification preferences.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15

- documents, document_versions, events: wedding-access RLS like tasks; couples (app.role =
  'client') only see rows shared with them (visibility = 'client').
- calendar_feeds: private iCal subscription tokens, one per member. Rows are visible to their
  own user only; the feed endpoint resolves a token through a SECURITY DEFINER function.
- notification_preferences: readable inside the organization (to decide whom to email),
  writable only by the user they belong to.
- audit_log: couples may write entries about their own actions (still not read them).
- notification_log: remembers which digests were sent, so a digest goes out once per day.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TZ = sa.DateTime(timezone=True)
ORG = "organization_id = app_current_org_id()"
OWN = f"{ORG} AND user_id = app_current_user_id()"
PROJECT_ACCESS = f"{ORG} AND app_can_access_project(project_id)"
NOT_CLIENT = "app_current_role() IS DISTINCT FROM 'client'"
SHARED = f"{NOT_CLIENT} OR visibility = 'client'"


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


def _project() -> sa.Column[object]:
    return sa.Column(
        "project_id",
        UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _user(name: str, *, nullable: bool = True, ondelete: str = "SET NULL") -> sa.Column[object]:
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable
    )


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TZ, server_default=sa.func.now(), nullable=False),
    ]


def _rls(table: str, using: str, *, force: bool = True) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    if force:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY access ON {table} USING ({using}) WITH CHECK ({using})")


def _restrict(table: str, condition: str) -> None:
    op.execute(f"CREATE POLICY client_scope ON {table} AS RESTRICTIVE USING ({condition})")


def _definer(signature: str, body: str) -> None:
    op.execute(body)
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_user")


def upgrade() -> None:
    # --- Documents -----------------------------------------------------------------------
    op.create_table(
        "documents",
        _id(),
        _org(),
        _project(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False, server_default="other"),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        sa.Column("current_version_id", UUID(as_uuid=True)),
        sa.Column("uploaded_by_type", sa.String(10), nullable=False, server_default="team"),
        _user("created_by"),
        sa.Column("deleted_at", TZ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_timestamps(),
        sa.CheckConstraint(
            "category IN ('contract', 'quote', 'invoice', 'planning', 'inspiration', 'other')",
            name="category",
        ),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
        sa.CheckConstraint("uploaded_by_type IN ('team', 'client')", name="uploaded_by_type"),
    )
    op.create_table(
        "document_versions",
        _id(),
        _org(),
        _project(),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False, unique=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("scan_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("scanned_at", TZ),
        _user("uploaded_by"),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "number", name="uq_document_versions_number"),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'clean', 'infected', 'failed', 'not_scanned')",
            name="scan_status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="size"),
    )
    op.create_foreign_key(
        "fk_documents_current_version_id_document_versions",
        "documents",
        "document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    _rls("documents", PROJECT_ACCESS)
    _rls("document_versions", PROJECT_ACCESS)
    _restrict("documents", SHARED)
    _restrict(
        "document_versions",
        f"{NOT_CLIENT} OR EXISTS (SELECT 1 FROM documents d WHERE d.id = document_id)",
    )

    # --- Calendar ------------------------------------------------------------------------
    op.create_table(
        "events",
        _id(),
        _org(),
        _project(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("starts_at", TZ, nullable=False),
        sa.Column("ends_at", TZ),
        sa.Column("all_day", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("location", sa.String(300)),
        sa.Column("description", sa.Text),
        sa.Column("visibility", sa.String(10), nullable=False, server_default="internal"),
        _user("created_by"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        *_timestamps(),
        sa.CheckConstraint("visibility IN ('internal', 'client')", name="visibility"),
        sa.CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="range"),
    )
    op.create_index("ix_events_project_starts", "events", ["project_id", "starts_at"])
    _rls("events", PROJECT_ACCESS)
    _restrict("events", SHARED)

    op.create_table(
        "calendar_feeds",
        _id(),
        _org(),
        sa.Column(
            "membership_id",
            UUID(as_uuid=True),
            sa.ForeignKey("memberships.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        _user("user_id", nullable=False, ondelete="CASCADE"),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", TZ),
        sa.Column("revoked_at", TZ),
    )
    # Not forced: app_calendar_feed_by_token() (schema owner) reads it before a tenant is known.
    _rls("calendar_feeds", OWN, force=False)
    _definer(
        "app_calendar_feed_by_token(text)",
        """
        CREATE FUNCTION app_calendar_feed_by_token(p_token_hash text)
        RETURNS TABLE (
            id uuid, organization_id uuid, user_id uuid, membership_id uuid, role text,
            timezone text, organization_name text
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$
            SELECT f.id, f.organization_id, f.user_id, f.membership_id, m.role,
                   o.timezone, o.name
            FROM calendar_feeds f
            JOIN memberships m ON m.id = f.membership_id
            JOIN organizations o ON o.id = f.organization_id
            WHERE f.token_hash = p_token_hash AND f.revoked_at IS NULL
              AND m.status = 'active' AND m.user_id = f.user_id AND o.status = 'active'
        $$
        """,
    )

    # --- Notifications -------------------------------------------------------------------
    op.create_table(
        "notification_preferences",
        _id(),
        _org(),
        _user("user_id", nullable=False, ondelete="CASCADE"),
        sa.Column("task_assigned", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("comments", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("documents", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("daily_digest", sa.Boolean, nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_notification_preferences_user"),
    )
    op.execute("ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_preferences FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY org_read ON notification_preferences FOR SELECT USING ({ORG})")
    op.execute(
        f"CREATE POLICY own_write ON notification_preferences USING ({OWN}) WITH CHECK ({OWN})"
    )

    op.create_table(
        "notification_log",
        _id(),
        _org(),
        _user("user_id", nullable=False, ondelete="CASCADE"),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("ref", sa.String(80), nullable=False),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "user_id", "kind", "ref", name="uq_notification_log_once"
        ),
    )
    _rls("notification_log", ORG)

    # Couples' own actions (e.g. uploads) are audited too: they may add audit entries, but
    # still never read the audit log.
    op.execute("DROP POLICY client_scope ON audit_log")
    op.execute(
        f"CREATE POLICY client_scope ON audit_log AS RESTRICTIVE FOR SELECT USING ({NOT_CLIENT})"
    )

    # The daily digest job runs without a request; it needs the active organizations first.
    _definer(
        "app_active_organizations()",
        """
        CREATE FUNCTION app_active_organizations()
        RETURNS TABLE (id uuid, timezone text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
        AS $$ SELECT o.id, o.timezone FROM organizations o WHERE o.status = 'active' $$
        """,
    )


def downgrade() -> None:
    op.execute("DROP POLICY client_scope ON audit_log")
    op.execute(f"CREATE POLICY client_scope ON audit_log AS RESTRICTIVE USING ({NOT_CLIENT})")
    op.execute("DROP FUNCTION app_active_organizations()")
    op.execute("DROP FUNCTION app_calendar_feed_by_token(text)")
    op.drop_table("notification_log")
    op.drop_table("notification_preferences")
    op.drop_table("calendar_feeds")
    op.drop_table("events")
    op.drop_constraint(
        "fk_documents_current_version_id_document_versions", "documents", type_="foreignkey"
    )
    op.drop_table("document_versions")
    op.drop_table("documents")
