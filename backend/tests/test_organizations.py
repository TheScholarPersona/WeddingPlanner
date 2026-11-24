from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import new_client
from tests.helpers import World, accept, build_world, last_email_to, send, token_from_link


@pytest.fixture
async def world(app: FastAPI) -> World:
    return await build_world(app)


def org(world: World, path: str = "") -> str:
    return f"/api/v1/orgs/{world.org_a}{path}"


async def test_update_organization_is_audited(world: World) -> None:
    admin = world["org_admin"].client

    response = await send(admin, "PATCH", org(world), json={"accent_color": "#4F6354"})
    log = (await admin.get(org(world, "/audit-log"), params={"action": "organization."})).json()

    assert response.status_code == 200
    assert response.json()["accent_color"] == "#4F6354"
    entry = log["items"][0]
    assert entry["action"] == "organization.updated"
    assert entry["actor_name"] == "Ada Admin"
    assert entry["changes"] == {"accent_color": {"old": None, "new": "#4F6354"}}


async def test_team_members_do_not_see_client_logins(world: World) -> None:
    as_admin = (await world["org_admin"].client.get(org(world, "/members"))).json()
    as_member = (await world["member"].client.get(org(world, "/members"))).json()

    assert {m["role"] for m in as_admin} == {"org_admin", "member", "client"}
    assert {m["role"] for m in as_member} == {"org_admin", "member"}


async def test_invitation_email_and_acceptance(app: FastAPI, world: World) -> None:
    admin = world["org_admin"].client

    created = await send(
        admin, "POST", org(world, "/invitations"), json={"email": "New@Example.com"}
    )
    token = token_from_link(last_email_to("new@example.com"), "invite")
    newcomer = await accept(app, token, "Nina New")
    pending = (await admin.get(org(world, "/invitations"))).json()

    assert created.status_code == 201
    assert created.json()["email"] == "new@example.com"
    assert (await newcomer.get(org(world))).status_code == 200
    assert pending == []


async def test_inviting_an_existing_member_is_rejected(world: World) -> None:
    response = await send(
        world["org_admin"].client,
        "POST",
        org(world, "/invitations"),
        json={"email": "member@example.com"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "already_member"


async def test_resending_invalidates_the_previous_link(app: FastAPI, world: World) -> None:
    admin = world["org_admin"].client
    created = (
        await send(admin, "POST", org(world, "/invitations"), json={"email": "n@example.com"})
    ).json()
    first = token_from_link(last_email_to("n@example.com"), "invite")

    await send(admin, "POST", org(world, f"/invitations/{created['id']}/resend"))
    second = token_from_link(last_email_to("n@example.com"), "invite")

    assert first != second
    assert (await new_client(app).get(f"/api/v1/auth/invitations/{first}")).status_code == 404
    assert (await new_client(app).get(f"/api/v1/auth/invitations/{second}")).status_code == 200


async def test_role_changes_need_a_recent_password_confirmation(
    world: World, owner_engine: AsyncEngine
) -> None:
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("UPDATE sessions SET reauth_at = :t"),
            {"t": datetime.now(UTC) - timedelta(hours=1)},
        )
    admin = world["org_admin"].client
    url = org(world, f"/members/{world['member'].membership_id}")

    blocked = await send(admin, "PATCH", url, json={"role": "org_admin"})
    reauth = await send(
        admin, "POST", "/api/v1/auth/reauth", json={"password": "correct horse battery staple"}
    )
    allowed = await send(admin, "PATCH", url, json={"role": "org_admin"})

    assert blocked.status_code == 403
    assert blocked.json()["code"] == "reauth_required"
    assert reauth.status_code == 204
    assert allowed.status_code == 200
    assert allowed.json()["role"] == "org_admin"


async def test_admins_cannot_change_their_own_membership(world: World) -> None:
    admin = world["org_admin"]

    response = await send(
        admin.client,
        "PATCH",
        org(world, f"/members/{admin.membership_id}"),
        json={"role": "member"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "cannot_change_self"


async def test_client_roles_cannot_be_promoted_to_team_roles(world: World) -> None:
    response = await send(
        world["org_admin"].client,
        "PATCH",
        org(world, f"/members/{world['client'].membership_id}"),
        json={"role": "member"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "client_role_fixed"


async def test_audit_log_is_paginated_newest_first(world: World) -> None:
    admin = world["org_admin"].client
    for name in ("One", "Two", "Three"):
        await send(admin, "PATCH", org(world), json={"name": name})

    first = (await admin.get(org(world, "/audit-log"), params={"limit": 2})).json()
    second = (
        await admin.get(
            org(world, "/audit-log"), params={"limit": 2, "cursor": first["next_cursor"]}
        )
    ).json()

    assert [i["changes"]["name"]["new"] for i in first["items"]] == ["Three", "Two"]
    assert second["items"][0]["changes"]["name"]["new"] == "One"


async def test_audit_log_cannot_be_modified_by_the_app(
    world: World, app_engine: AsyncEngine
) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        async with app_engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log"))


async def test_memberships_of_other_tenants_are_invisible_in_sql(
    world: World, app_engine: AsyncEngine
) -> None:
    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.org_id', :o, true)"), {"o": str(world.org_b)}
        )
        orgs = (
            await conn.execute(text("SELECT DISTINCT organization_id FROM memberships"))
        ).scalars()
        assert set(orgs) == {world.org_b}


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_revoking_a_team_invitation_voids_the_link(app: FastAPI, world: World) -> None:
    admin = world["org_admin"].client
    created = (
        await send(admin, "POST", org(world, "/invitations"), json={"email": "late@example.com"})
    ).json()
    token = token_from_link(last_email_to("late@example.com"), "invite")

    revoked = await send(admin, "DELETE", org(world, f"/invitations/{created['id']}"))
    pending = (await admin.get(org(world, "/invitations"))).json()
    link = await new_client(app).get(f"/api/v1/auth/invitations/{token}")
    log = (await admin.get(org(world, "/audit-log"), params={"action": "invitation."})).json()

    assert revoked.status_code == 204
    assert pending == []
    assert link.json()["code"] == "invitation_invalid"
    assert log["items"][0]["action"] == "invitation.revoked"
