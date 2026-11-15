from fastapi import APIRouter

from app.authz.deps import DbSession, OrgContext, require
from app.authz.permissions import Perm
from app.notifications import service
from app.notifications.schemas import PreferencesIn, PreferencesOut

router = APIRouter(prefix="/orgs/{org_id}/notification-preferences", tags=["notifications"])


@router.get("", response_model=PreferencesOut)
async def get_preferences(
    db: DbSession, ctx: OrgContext = require(Perm.ORG_READ)
) -> PreferencesOut:
    return await service.get_preferences(db, ctx)


@router.patch("", response_model=PreferencesOut)
async def update_preferences(
    body: PreferencesIn, db: DbSession, ctx: OrgContext = require(Perm.ORG_READ)
) -> PreferencesOut:
    return await service.update_preferences(db, ctx, body)
