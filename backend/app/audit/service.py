"""Audit trail for security- and business-relevant changes.

Entries are written in the same transaction as the change they describe. Sensitive values are
never stored; pass field names with `masked` where only the fact of a change matters.
"""

import uuid
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.core.context import current_request

ActorType = Literal["user", "platform_admin", "system"]

SENSITIVE_FIELDS = frozenset({"password", "password_hash", "token", "token_hash", "totp_secret"})


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Changed fields as {"field": {"old": ..., "new": ...}}, sensitive values masked."""
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old != new:
            if key in SENSITIVE_FIELDS:
                changes[key] = {"changed": True}
            else:
                changes[key] = {"old": _jsonable(old), "new": _jsonable(new)}
    return changes


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def record(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_type: ActorType = "user",
    changes: dict[str, Any] | None = None,
) -> None:
    info = current_request()
    session.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type if actor_user_id or actor_type != "user" else "system",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes or None,
            ip=info.ip if info else None,
            user_agent=info.user_agent if info else None,
            request_id=info.request_id if info else None,
        )
    )
    await session.flush()
