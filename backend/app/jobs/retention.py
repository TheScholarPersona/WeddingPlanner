"""Daily cleanup of data that is no longer needed (storage limitation, Art. 5(1)(e) GDPR).

- expired or revoked sessions, used reset links, stale invitations, revoked calendar links and
  old support grants (SECURITY DEFINER app_purge_expired());
- per organization: the digest log after 90 days, and couples' access to weddings that were
  archived longer ago than the organization allows.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text

from app.db.session import get_sessionmaker
from app.db.tenant import set_tenant_context
from app.notifications.models import NotificationLog
from app.organizations.models import Organization
from app.projects.models import Project, ProjectMember, ProjectRole

logger = logging.getLogger(__name__)
NIL = uuid.UUID(int=0)


async def purge(_: dict[str, Any]) -> dict[str, int]:
    removed: dict[str, int] = {}
    async with get_sessionmaker()() as db:
        for item, count in (await db.execute(text("SELECT * FROM app_purge_expired()"))).all():
            removed[item] = int(count)
        orgs = (await db.execute(text("SELECT id FROM app_active_organizations()"))).scalars()
        org_ids = list(orgs)
        await db.commit()

        now = datetime.now(UTC)
        log_total = access_total = 0
        for org_id in org_ids:
            await set_tenant_context(db, organization_id=org_id, user_id=NIL, role="org_admin")
            log_total += (
                await db.execute(
                    delete(NotificationLog).where(
                        NotificationLog.created_at < now - timedelta(days=90)
                    )
                )
            ).rowcount or 0  # type: ignore[attr-defined]
            org = await db.get(Organization, org_id)
            assert org is not None
            cutoff = now - timedelta(days=org.client_access_days_after_archive)
            ended = select(Project.id).where(
                Project.archived_at.is_not(None), Project.archived_at < cutoff
            )
            access_total += (
                await db.execute(
                    delete(ProjectMember).where(
                        ProjectMember.project_role == ProjectRole.CLIENT,
                        ProjectMember.project_id.in_(ended),
                    )
                )
            ).rowcount or 0  # type: ignore[attr-defined]
            await db.commit()
        removed["notification_log"] = log_total
        removed["couple_access_after_archive"] = access_total
    logger.info("retention cleanup", extra={"removed": removed})
    return removed
