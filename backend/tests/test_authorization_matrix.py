"""The rights matrix from "Rollen und Berechtigungen", executed against every org endpoint.

Roles: org_admin, member and client of org A; `outsider` is the admin of org B; `anonymous` has
no session. Outsiders get 404 so that other tenants' resources are never revealed.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI

from tests.helpers import World, build_world, send

ROLES = ("org_admin", "member", "client", "outsider", "anonymous")


def _invitation_id(world: World) -> str:
    return str(world.users["pending_invitation"].membership_id)


Case = tuple[str, str, Callable[[World], dict[str, Any] | None], tuple[int, int, int, int, int]]

# Columns: method, path under /orgs/{org_a}, body, expected status per role in ROLES order
MATRIX: list[Case] = [
    ("GET", "", lambda w: None, (200, 200, 200, 404, 401)),
    ("PATCH", "", lambda w: {"name": "Renamed"}, (200, 403, 403, 404, 401)),
    ("GET", "/members", lambda w: None, (200, 200, 403, 404, 401)),
    ("PATCH", "/members/{member}", lambda w: {"status": "disabled"}, (200, 403, 403, 404, 401)),
    ("GET", "/invitations", lambda w: None, (200, 403, 403, 404, 401)),
    ("POST", "/invitations", lambda w: {"email": "new@example.com"}, (201, 403, 403, 404, 401)),
    ("POST", "/invitations/{invitation}/resend", lambda w: None, (200, 403, 403, 404, 401)),
    ("DELETE", "/invitations/{invitation}", lambda w: None, (204, 403, 403, 404, 401)),
    ("GET", "/audit-log", lambda w: None, (200, 403, 403, 404, 401)),
]


@pytest.fixture
async def world(app: FastAPI) -> World:
    world = await build_world(app)
    response = await send(
        world["org_admin"].client,
        "POST",
        f"/api/v1/orgs/{world.org_a}/invitations",
        json={"email": "pending@example.com"},
    )
    assert response.status_code == 201
    from tests.helpers import Member

    world.users["pending_invitation"] = Member(
        world["anonymous"].client, "", uuid.UUID(response.json()["id"])
    )
    return world


@pytest.mark.parametrize(("method", "path", "body", "expected"), MATRIX, ids=lambda v: str(v))
@pytest.mark.parametrize("role_index", range(len(ROLES)), ids=ROLES)
async def test_rights_matrix(
    world: World,
    method: str,
    path: str,
    body: Callable[[World], dict[str, Any] | None],
    expected: tuple[int, ...],
    role_index: int,
) -> None:
    role = ROLES[role_index]
    url = f"/api/v1/orgs/{world.org_a}" + path.format(
        member=world["member"].membership_id, invitation=_invitation_id(world)
    )
    payload = body(world)
    response = await send(
        world[role].client, method, url, **({"json": payload} if payload is not None else {})
    )

    assert response.status_code == expected[role_index], response.text
    if response.status_code >= 400:
        assert response.headers["content-type"] == "application/problem+json"


async def test_outsider_cannot_reach_foreign_resources_through_own_org(world: World) -> None:
    """An admin of org B uses org B's path with ids that belong to org A."""
    outsider = world["outsider"].client
    base = f"/api/v1/orgs/{world.org_b}"

    member = await send(
        outsider,
        "PATCH",
        f"{base}/members/{world['member'].membership_id}",
        json={"status": "disabled"},
    )
    invitation = await send(outsider, "DELETE", f"{base}/invitations/{_invitation_id(world)}")
    members = await outsider.get(f"{base}/members")

    assert member.status_code == 404
    assert invitation.status_code == 404
    assert {m["email"] for m in members.json()} == {"outsider@example.com"}


async def test_disabled_member_loses_access_immediately(world: World) -> None:
    admin = world["org_admin"].client
    response = await send(
        admin,
        "PATCH",
        f"/api/v1/orgs/{world.org_a}/members/{world['member'].membership_id}",
        json={"status": "disabled"},
    )
    assert response.status_code == 200

    after = await world["member"].client.get(f"/api/v1/orgs/{world.org_a}")
    me = await world["member"].client.get("/api/v1/me")

    assert after.status_code == 404
    assert me.json()["memberships"] == []
