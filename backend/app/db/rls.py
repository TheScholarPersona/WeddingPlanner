"""SQL builders for row-level security, used by Alembic migrations.

Every tenant table calls `enable_tenant_rls(table)` in the migration that creates it.
"""

import re

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _check(identifier: str) -> str:
    if not _IDENTIFIER.match(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return identifier


def enable_tenant_rls(table: str, *, force: bool = True) -> list[str]:
    """Statements that restrict `table` to rows of the organization in `app.org_id`.

    FORCE makes the policy apply to the table owner too, so nothing bypasses it by accident.
    Use `force=False` only for tables that a reviewed SECURITY DEFINER function (owned by the
    schema owner) must read before a tenant is known, e.g. looking up an invitation token.
    """
    t = _check(table)
    statements = [f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY"]
    if force:
        statements.append(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
    statements.append(
        f"CREATE POLICY tenant_isolation ON {t} "
        "USING (organization_id = app_current_org_id()) "
        "WITH CHECK (organization_id = app_current_org_id())"
    )
    return statements


def disable_tenant_rls(table: str) -> list[str]:
    t = _check(table)
    return [
        f"DROP POLICY IF EXISTS tenant_isolation ON {t}",
        f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY",
    ]
