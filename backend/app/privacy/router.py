import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from app.auth import service as auth_service
from app.authz.deps import (
    CurrentUser,
    DbSession,
    OrgContext,
    ProjectContext,
    require,
    require_project,
    require_recent_auth,
)
from app.authz.permissions import Perm, ProjectPerm
from app.core.errors import ProblemError
from app.core.security import verify_password
from app.portal.service import Access, PortalAccess
from app.privacy import service
from app.privacy.schemas import (
    ConsentIn,
    ConsentOut,
    CoupleConsentsOut,
    DeleteAccountIn,
    EraseClientIn,
    EraseSummaryOut,
)

router = APIRouter(tags=["privacy"])

PRIVATE_DOWNLOAD = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/orgs/{org_id}/clients/{client_id}/export", response_class=Response)
async def export_client(
    client_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.PRIVACY_MANAGE)
) -> Response:
    """Everything stored about a client, as a ZIP (data.json plus document files)."""
    filename, data = await service.export_client(db, ctx, client_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            **PRIVATE_DOWNLOAD,
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/orgs/{org_id}/clients/{client_id}/erase", response_model=EraseSummaryOut)
async def erase_client(
    client_id: uuid.UUID,
    body: EraseClientIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.PRIVACY_MANAGE),
) -> EraseSummaryOut:
    require_recent_auth(ctx)
    return EraseSummaryOut(**await service.erase_client(db, ctx, client_id, body.confirm))


@router.get("/orgs/{org_id}/projects/{project_id}/consents", response_model=list[CoupleConsentsOut])
async def couple_consents(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.READ)
) -> list[CoupleConsentsOut]:
    return await service.couple_consents(db, ctx)


@router.get("/portal/projects/{project_id}/consents", response_model=list[ConsentOut])
async def my_consents(db: DbSession, access: PortalAccess = Access) -> list[ConsentOut]:
    return await service.my_consents(db, access.ctx)


@router.put("/portal/projects/{project_id}/consents", response_model=list[ConsentOut])
async def decide(body: ConsentIn, db: DbSession, access: PortalAccess = Access) -> list[ConsentOut]:
    return await service.decide(db, access.ctx, body.kind, body.granted)


@router.get("/me/export", response_class=JSONResponse)
async def export_me(auth: CurrentUser, db: DbSession) -> JSONResponse:
    data: dict[str, Any] = await service.export_me(db, auth.user)
    return JSONResponse(
        data,
        headers={
            **PRIVATE_DOWNLOAD,
            "Content-Disposition": (
                f'attachment; filename="my-data-{datetime.now(UTC):%Y%m%d}.json"'
            ),
        },
    )


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountIn, auth: CurrentUser, response: Response, db: DbSession
) -> None:
    if not verify_password(auth.user.password_hash, body.password):
        raise ProblemError(
            400,
            "invalid_current_password",
            "Password incorrect",
            "The password is incorrect.",
        )
    await service.delete_account(db, auth.user)
    auth_service.clear_session_cookies(response)
