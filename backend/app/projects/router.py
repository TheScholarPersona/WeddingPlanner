import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Response, status

from app.authz.deps import DbSession, OrgContext, ProjectContext, require, require_project
from app.authz.permissions import Perm, ProjectPerm
from app.projects import service
from app.projects.schemas import (
    DashboardOut,
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectMemberIn,
    ProjectMemberOut,
    ProjectMemberUpdateIn,
    ProjectStatusT,
    ProjectSummaryOut,
    ProjectUpdateIn,
    ProjectVendorIn,
    ProjectVendorOut,
    ProjectVendorUpdateIn,
)

router = APIRouter(prefix="/orgs/{org_id}", tags=["weddings"])
P = "/projects/{project_id}"


def _etag(response: Response, detail: ProjectDetailOut) -> ProjectDetailOut:
    response.headers["ETag"] = f'"{detail.version}"'
    return detail


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(db: DbSession, ctx: OrgContext = require(Perm.DASHBOARD_READ)) -> DashboardOut:
    return await service.dashboard(db, ctx)


@router.get("/projects", response_model=list[ProjectSummaryOut])
async def list_projects(
    db: DbSession,
    ctx: OrgContext = require(Perm.PROJECTS_LIST),
    status: ProjectStatusT | None = None,
    scope: Literal["all", "mine"] = "all",
) -> list[ProjectSummaryOut]:
    return await service.list_projects(db, ctx, status, scope == "mine")


@router.post("/projects", response_model=ProjectDetailOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateIn,
    response: Response,
    db: DbSession,
    ctx: OrgContext = require(Perm.PROJECTS_CREATE),
) -> ProjectDetailOut:
    project = await service.create_project(db, ctx, body)
    project_ctx = ProjectContext(
        user=ctx.user,
        session=ctx.session,
        membership=ctx.membership,
        organization_id=ctx.organization_id,
        project=project,
        project_role="admin" if ctx.role == "org_admin" else "lead",
    )
    response.headers["Location"] = f"/api/v1/orgs/{ctx.organization_id}/projects/{project.id}"
    return _etag(response, await service.get_project(db, project_ctx))


@router.get(P, response_model=ProjectDetailOut)
async def get_project(
    response: Response, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.READ)
) -> ProjectDetailOut:
    return _etag(response, await service.get_project(db, ctx))


@router.patch(P, response_model=ProjectDetailOut)
async def update_project(
    body: ProjectUpdateIn,
    response: Response,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
    ctx: ProjectContext = require_project(ProjectPerm.UPDATE),
) -> ProjectDetailOut:
    await service.update_project(db, ctx, body, if_match)
    return _etag(response, await service.get_project(db, ctx))


@router.post(f"{P}/archive", response_model=ProjectDetailOut)
async def archive_project(
    response: Response, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.ARCHIVE)
) -> ProjectDetailOut:
    await service.set_archived(db, ctx, True)
    return _etag(response, await service.get_project(db, ctx))


@router.post(f"{P}/restore", response_model=ProjectDetailOut)
async def restore_project(
    response: Response, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.ARCHIVE)
) -> ProjectDetailOut:
    await service.set_archived(db, ctx, False)
    return _etag(response, await service.get_project(db, ctx))


@router.delete(P, status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.DELETE)
) -> None:
    await service.delete_project(db, ctx)


@router.get(f"{P}/members", response_model=list[ProjectMemberOut])
async def list_members(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.READ)
) -> list[ProjectMemberOut]:
    return await service.list_members(db, ctx)


@router.post(f"{P}/members", response_model=list[ProjectMemberOut], status_code=201)
async def add_member(
    body: ProjectMemberIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.MANAGE_TEAM),
) -> list[ProjectMemberOut]:
    await service.add_member(db, ctx, body)
    return await service.list_members(db, ctx)


@router.patch(f"{P}/members/{{member_id}}", response_model=list[ProjectMemberOut])
async def update_member(
    member_id: uuid.UUID,
    body: ProjectMemberUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.MANAGE_TEAM),
) -> list[ProjectMemberOut]:
    await service.update_member(db, ctx, member_id, body)
    return await service.list_members(db, ctx)


@router.delete(f"{P}/members/{{member_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.MANAGE_TEAM),
) -> None:
    await service.remove_member(db, ctx, member_id)


@router.get(f"{P}/vendors", response_model=list[ProjectVendorOut])
async def list_vendors(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.VENDORS_READ)
) -> list[ProjectVendorOut]:
    return await service.list_vendors(db, ctx)


@router.post(f"{P}/vendors", response_model=ProjectVendorOut, status_code=201)
async def add_vendor(
    body: ProjectVendorIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.VENDORS_MANAGE),
) -> ProjectVendorOut:
    return await service.add_vendor(db, ctx, body)


@router.patch(f"{P}/vendors/{{link_id}}", response_model=ProjectVendorOut)
async def update_vendor(
    link_id: uuid.UUID,
    body: ProjectVendorUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.VENDORS_MANAGE),
) -> ProjectVendorOut:
    return await service.update_vendor(db, ctx, link_id, body)


@router.delete(f"{P}/vendors/{{link_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_vendor(
    link_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.VENDORS_MANAGE),
) -> None:
    await service.remove_vendor(db, ctx, link_id)
