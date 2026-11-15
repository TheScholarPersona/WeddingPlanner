"""Building blocks for API tests: organizations, users and signed-in clients (fake data only)."""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response

from app.db.session import get_sessionmaker
from app.db.tenant import set_tenant_context
from app.notifications.mailer import OUTBOX
from app.organizations.models import Organization, OrgRole
from app.organizations.service import _create_invitation, create_organization
from tests.conftest import new_client

PASSWORD = "correct horse battery staple"


def token_from_link(text: str, kind: str) -> str:
    match = re.search(rf"/{kind}[/?](?:token=)?([A-Za-z0-9_\-]+)", text)
    assert match, f"no {kind} link in: {text}"
    return match.group(1)


def last_email_to(address: str) -> str:
    for email in reversed(OUTBOX):
        if email.to == address:
            return email.text
    raise AssertionError(f"no email to {address}")


async def send(client: AsyncClient, method: str, url: str, **kwargs: Any) -> Response:
    """Like a browser app: send the CSRF cookie value back in the header."""
    headers = dict(kwargs.pop("headers", {}) or {})
    csrf = client.cookies.get("__Host-csrf")
    if csrf:
        headers.setdefault("X-CSRF-Token", csrf)
    return await client.request(method, url, headers=headers, **kwargs)


async def new_organization(name: str, admin_email: str) -> tuple[uuid.UUID, str]:
    async with get_sessionmaker()() as db:
        org, link = await create_organization(db, name=name, admin_email=admin_email)
        await db.commit()
    return org.id, token_from_link(link, "invite")


async def invite_directly(org_id: uuid.UUID, email: str, role: OrgRole) -> str:
    """Create an invitation without the API (e.g. client logins, which come from projects)."""
    async with get_sessionmaker()() as db:
        await set_tenant_context(
            db, organization_id=org_id, user_id=uuid.UUID(int=0), role="org_admin"
        )
        org = await db.get(Organization, org_id)
        assert org is not None
        _, link = await _create_invitation(db, org, email, role, None)
        await db.commit()
    return token_from_link(link, "invite")


async def accept(app: FastAPI, token: str, name: str, password: str = PASSWORD) -> AsyncClient:
    client = new_client(app)
    response = await client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": name, "password": password}
    )
    assert response.status_code == 200, response.text
    return client


@dataclass
class Member:
    client: AsyncClient
    email: str
    membership_id: uuid.UUID | None = None


@dataclass
class World:
    org_a: uuid.UUID
    org_b: uuid.UUID
    users: dict[str, Member] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Member:
        return self.users[key]


async def build_world(app: FastAPI) -> World:
    """Org A: admin, member, client. Org B: admin (the outsider for org A)."""
    org_a, admin_token = await new_organization("Atelier Test", "admin@example.com")
    org_b, other_token = await new_organization("Other Agency", "outsider@example.com")
    world = World(org_a=org_a, org_b=org_b)

    world.users["org_admin"] = Member(
        await accept(app, admin_token, "Ada Admin"), "admin@example.com"
    )
    world.users["outsider"] = Member(
        await accept(app, other_token, "Otto Outsider"), "outsider@example.com"
    )
    member_token = await invite_directly(org_a, "member@example.com", OrgRole.MEMBER)
    world.users["member"] = Member(
        await accept(app, member_token, "Max Member"), "member@example.com"
    )
    client_token = await invite_directly(org_a, "client@example.com", OrgRole.CLIENT)
    world.users["client"] = Member(
        await accept(app, client_token, "Cleo Client"), "client@example.com"
    )
    world.users["anonymous"] = Member(new_client(app), "")

    members = (await world["org_admin"].client.get(f"/api/v1/orgs/{org_a}/members")).json()
    for member in members:
        for user in world.users.values():
            if user.email == member["email"]:
                user.membership_id = uuid.UUID(member["id"])
    return world
