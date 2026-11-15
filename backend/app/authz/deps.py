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
from app.authz.permissions import Perm, has_perm
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.security import hash_token, tokens_match
from app.db.session import get_session
from app.db.tenant import set_tenant_context
from app.organizations.models import Membership, MembershipStatus, Organization

DbSession = Annotated[AsyncSession, Depends(get_session)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-csrf-token"

NOT_AUTHENTICATED = ProblemError(
    401, "not_authenticated", "Please sign in", "Your session has ended. Please sign in again."
)


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


async def get_authenticated(request: Request, db: DbSession) -> Authenticated:
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
    if user_session.revoked_at is not None or user_session.expires_at <= now:
        raise NOT_AUTHENTICATED

    if now - user_session.last_seen_at > timedelta(minutes=5):
        user_session.last_seen_at = now

    await db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user.id)})
    return Authenticated(user=user, session=user_session)


CurrentUser = Annotated[Authenticated, Depends(get_authenticated)]


def require(perm: Perm) -> Any:
    """Dependency factory for organization routes: `ctx: OrgContext = require(Perm.X)`."""

    async def dependency(org_id: uuid.UUID, auth: CurrentUser, db: DbSession) -> OrgContext:
        membership = (
            await db.execute(
                select(Membership)
                .join(Organization, Organization.id == Membership.organization_id)
                .where(
                    Membership.organization_id == org_id,
                    Membership.user_id == auth.user.id,
                    Membership.status == MembershipStatus.ACTIVE,
                    Organization.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise not_found()
        if not has_perm(membership.role, perm):
            raise ProblemError(
                403, "forbidden", "Not allowed", "Your role does not allow this action."
            )

        await set_tenant_context(
            db,
            organization_id=org_id,
            user_id=auth.user.id,
            role=membership.role,  # type: ignore[arg-type]
        )
        return OrgContext(
            user=auth.user, session=auth.session, membership=membership, organization_id=org_id
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
