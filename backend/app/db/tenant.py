"""Tenant context for PostgreSQL row-level security.

The values are set with `set_config(..., is_local => true)`, so they only live for the current
transaction and can never leak into another request through a pooled connection.
RLS policies read them through the SQL functions created in migration 0001.
"""

import uuid
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TenantRole = Literal["org_admin", "member", "client", "support"]


async def set_tenant_context(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: TenantRole,
) -> None:
    await session.execute(
        text(
            "SELECT set_config('app.org_id', :org_id, true),"
            " set_config('app.user_id', :user_id, true),"
            " set_config('app.role', :role, true)"
        ),
        {"org_id": str(organization_id), "user_id": str(user_id), "role": role},
    )
