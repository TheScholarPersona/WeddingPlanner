"""Request authentication and authorization dependencies.

Every route under /orgs/{org_id} must depend on `require(...)`; a test enforces this.
`require` checks the session, the active membership and the permission, then sets the tenant
context so that PostgreSQL row-level security applies to everything the request does.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserSession
from app.authz.permissions import (
    ADMIN_PROJECT_ROLE,
    Perm,
    ProjectPerm,
    has_perm,
    has_project_perm,
)
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.security import hash_token, tokens_match
from app.db.session import get_session
from app.db.tenant import set_tenant_context
from app.organizations.models import Membership, MembershipStatus, Organization, OrgRole
from app.projects.models import Project, ProjectMember

DbSession = Annotated[AsyncSession, Depends(get_session)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-csrf-token"

NOT_AUTHENTICATED = ProblemError(
    401, "not_authenticated", "Please sign in", "Your session has ended. Please sign in again."
)


TWO_FACTOR_PENDING = ProblemError(
    401, "two_factor_pending", "Enter your code", "Enter the code from your authenticator app."
)
TWO_FACTOR_REQUIRED = ProblemError(
    403,
    "two_factor_required",
    "Two-factor authentication required",
    "Your organization requires two-factor authentication. Turn it on in your account.",
)

FORBIDDEN = ProblemError(403, "forbidden", "Not allowed", "Your role does not allow this action.")


def not_found() -> ProblemError:
    # Used for resources in other tenants too, so their existence is never revealed.
    return ProblemError(404, "not_found", "Not Found")


@dataclass
class Authenticated:
    user: User
    session: UserSession


@dataclass
class OrgContext:
    user: User
    session: UserSession
    membership: Membership
    organization_id: uuid.UUID

    @property
    def role(self) -> str:
        return self.membership.role


async def _load_session(request: Request, db: AsyncSession, *, pending: bool) -> Authenticated:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise NOT_AUTHENTICATED

    # Double-submit CSRF check for every state-changing request made with a session cookie.
    if request.method not in SAFE_METHODS:
        cookie = request.cookies.get(settings.csrf_cookie_name, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not header or not tokens_match(cookie, header):
            raise ProblemError(
                403, "csrf_failed", "Request blocked", "Please reload the page and try again."
            )

    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_token(token))
        )
    ).one_or_none()
    if row is None:
        raise NOT_AUTHENTICATED
    user_session, user = row
    if (
        user_session.revoked_at is not None
        or user_session.expires_at <= now
        or user.deleted_at is not None
    ):
        raise NOT_AUTHENTICATED
    if user_session.mfa_pending != pending:
        # A password-only session can do nothing but complete the second step (and vice versa).
        raise TWO_FACTOR_PENDING if user_session.mfa_pending else NOT_AUTHENTICATED

    if now - user_session.last_seen_at > timedelta(minutes=5):
        user_session.last_seen_at = now

    await db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user.id)})
    return Authenticated(user=user, session=user_session)


async def get_authenticated(request: Request, db: DbSession) -> Authenticated:
    return await _load_session(request, db, pending=False)


async def get_pending_two_factor(request: Request, db: DbSession) -> Authenticated:
    """The session after a correct password, before the second factor was entered."""
    return await _load_session(request, db, pending=True)


CurrentUser = Annotated[Authenticated, Depends(get_authenticated)]
PendingTwoFactor = Annotated[Authenticated, Depends(get_pending_two_factor)]


async def _org_context(
    org_id: uuid.UUID, auth: Authenticated, db: AsyncSession, perm: Perm | None
) -> OrgContext:
    row = (
        await db.execute(
            select(Membership, Organization.require_2fa)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.organization_id == org_id,
                Membership.user_id == auth.user.id,
                Membership.status == MembershipStatus.ACTIVE,
                Organization.status == "active",
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    membership, require_2fa = row
    if require_2fa and membership.role != OrgRole.CLIENT and not auth.user.two_factor_enabled:
        raise TWO_FACTOR_REQUIRED
    if perm is not None and not has_perm(membership.role, perm):
        raise FORBIDDEN

    await set_tenant_context(
        db,
        organization_id=org_id,
        user_id=auth.user.id,
        role=membership.role,  # type: ignore[arg-type]
    )
    return OrgContext(
        user=auth.user, session=auth.session, membership=membership, organization_id=org_id
    )


def require(perm: Perm) -> Any:
    """Dependency factory for organization routes: `ctx: OrgContext = require(Perm.X)`."""

    async def dependency(org_id: uuid.UUID, auth: CurrentUser, db: DbSession) -> OrgContext:
        return await _org_context(org_id, auth, db, perm)

    dependency.__authz_permission__ = perm  # type: ignore[attr-defined]
    return Depends(dependency)


@dataclass
class ProjectContext(OrgContext):
    project: Project
    project_role: str

    def can(self, perm: ProjectPerm) -> bool:
        return has_project_perm(self.project_role, perm)


def require_project(perm: ProjectPerm) -> Any:
    """Dependency factory for wedding routes under /orgs/{org_id}/projects/{project_id}.

    The project is loaded under row-level security, so weddings the user is not assigned to
    are simply not found.
    """

    async def dependency(
        org_id: uuid.UUID, project_id: uuid.UUID, auth: CurrentUser, db: DbSession
    ) -> ProjectContext:
        ctx = await _org_context(org_id, auth, db, None)
        project = (
            await db.execute(
                select(Project).where(Project.id == project_id, Project.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if project is None:
            raise not_found()

        if ctx.role == OrgRole.ORG_ADMIN:
            project_role: str | None = ADMIN_PROJECT_ROLE
        else:
            project_role = (
                await db.execute(
                    select(ProjectMember.project_role).where(
                        ProjectMember.project_id == project.id,
                        ProjectMember.membership_id == ctx.membership.id,
                    )
                )
            ).scalar_one_or_none()
        if project_role is None:
            raise not_found()
        if not has_project_perm(project_role, perm):
            raise FORBIDDEN
        return ProjectContext(
            user=ctx.user,
            session=ctx.session,
            membership=ctx.membership,
            organization_id=ctx.organization_id,
            project=project,
            project_role=project_role,
        )

    dependency.__authz_permission__ = perm  # type: ignore[attr-defined]
    return Depends(dependency)


def require_recent_auth(ctx: OrgContext) -> None:
    """Sensitive actions need a password confirmation from the last few minutes."""
    window = timedelta(minutes=get_settings().reauth_window_minutes)
    reauth_at = ctx.session.reauth_at
    if reauth_at is None or datetime.now(UTC) - reauth_at > window:
        raise ProblemError(
            403,
            "reauth_required",
            "Please confirm your password",
            "For your security, confirm your password to continue.",
        )
