import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, Path, Response, status

from app.authz.deps import (
    DbSession,
    OrgContext,
    ProjectContext,
    not_found,
    require,
    require_project,
)
from app.authz.permissions import Perm, ProjectPerm
from app.core import ratelimit
from app.core.context import current_request
from app.events import service
from app.events.schemas import CalendarItemOut, EventIn, EventOut, FeedCreatedOut, FeedOut

router = APIRouter(tags=["calendar"])
IfMatch = Annotated[str | None, Header()]
P = "/orgs/{org_id}/projects/{project_id}/events"


@router.get(P, response_model=list[EventOut])
async def list_events(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.READ)
) -> list[EventOut]:
    return await service.list_events(db, ctx)


@router.post(P, response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventIn, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.EVENTS_WRITE)
) -> EventOut:
    return await service.create_event(db, ctx, body)


@router.put(P + "/{event_id}", response_model=EventOut)
async def update_event(
    event_id: uuid.UUID,
    body: EventIn,
    db: DbSession,
    if_match: IfMatch = None,
    ctx: ProjectContext = require_project(ProjectPerm.EVENTS_WRITE),
) -> EventOut:
    return await service.update_event(db, ctx, event_id, body, if_match)


@router.delete(P + "/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.EVENTS_WRITE),
) -> None:
    await service.delete_event(db, ctx, event_id)


@router.get("/orgs/{org_id}/calendar", response_model=list[CalendarItemOut])
async def calendar(
    db: DbSession,
    start: date,
    end: date,
    project_id: uuid.UUID | None = None,
    mine: bool = False,
    ctx: OrgContext = require(Perm.CALENDAR_READ),
) -> list[CalendarItemOut]:
    service.check_range(start, end)
    viewer = service.Viewer(ctx.organization_id, ctx.membership.id, is_client=False)
    return await service.collect(db, viewer, start, end, project_id=project_id, mine=mine)


@router.get("/orgs/{org_id}/calendar/feed", response_model=FeedOut)
async def get_feed(db: DbSession, ctx: OrgContext = require(Perm.ORG_READ)) -> FeedOut:
    return await service.get_feed(db, ctx)


@router.post("/orgs/{org_id}/calendar/feed", response_model=FeedCreatedOut, status_code=201)
async def create_feed(db: DbSession, ctx: OrgContext = require(Perm.ORG_READ)) -> FeedCreatedOut:
    return await service.create_feed(db, ctx)


@router.delete("/orgs/{org_id}/calendar/feed", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_feed(db: DbSession, ctx: OrgContext = require(Perm.ORG_READ)) -> None:
    await service.revoke_feed(db, ctx)


@router.get(
    "/calendar-feeds/{token}.ics",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}},
)
async def feed(
    db: DbSession, token: Annotated[str, Path(min_length=20, max_length=100)]
) -> Response:
    """Public subscription URL: the secret token in the path is the only credential."""
    info = current_request()
    await ratelimit.enforce([f"feed:{info.ip if info else 'unknown'}"], 60)
    body = await service.render_feed(db, token)
    if body is None:
        raise not_found()
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300", "X-Robots-Tag": "noindex"},
    )
