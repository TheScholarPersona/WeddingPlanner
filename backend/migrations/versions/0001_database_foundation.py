"""Database foundation: privileges for the runtime role and RLS helper functions.

The login roles `app_user` (runtime, no BYPASSRLS) and `admin_api` (platform admin API) are
created outside migrations, with passwords from the environment
(docker/postgres/initdb/01-roles.sh locally, the test fixtures in tests).

Revision ID: 0001
Revises:
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only the owner may create objects in the schema.
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO app_user, admin_api")

    # Tables created by migrations are usable by the runtime role; RLS still applies.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_user"
    )

    # Tenant context, set per transaction by app.db.tenant.set_tenant_context().
    # An unset value yields NULL, and `organization_id = NULL` matches no row.
    op.execute(
        """
        CREATE FUNCTION app_current_org_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT nullif(current_setting('app.org_id', true), '')::uuid $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_current_user_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION app_current_role() RETURNS text
        LANGUAGE sql STABLE PARALLEL SAFE
        AS $$ SELECT nullif(current_setting('app.role', true), '') $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_current_role()")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app_current_org_id()")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_user"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM app_user, admin_api")
