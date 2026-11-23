"""Platform administration and support access granted by organizations."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers import World, build_world, send
from tests.test_two_factor import reauth, turn_on


@pytest.fixture
async def world(app: FastAPI) -> World:
    return await build_world(app)


async def make_admin(owner_engine: AsyncEngine, email: str) -> None:
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = :e"), {"e": email}
        )


@pytest.fixture
async def admin(world: World, owner_engine: AsyncEngine) -> AsyncClient:
    """The outsider (admin of org B) is also a platform admin, with 2FA on."""
    await make_admin(owner_engine, "outsider@example.com")
    client = world["outsider"].client
    await turn_on(client)
    return client


async def test_admin_area_is_hidden_from_everyone_else(
    world: World, owner_engine: AsyncEngine
) -> None:
    for role in ("org_admin", "member", "client"):
        assert (await world[role].client.get("/api/v1/admin/organizations")).status_code == 404
    assert (await world["anonymous"].client.get("/api/v1/admin/organizations")).status_code == 401

    await make_admin(owner_engine, "member@example.com")
    no_2fa = await world["member"].client.get("/api/v1/admin/organizations")
    assert no_2fa.status_code == 403
    assert no_2fa.json()["code"] == "two_factor_required"


async def test_list_create_and_suspend_organizations(world: World, admin: AsyncClient) -> None:
    orgs = (await admin.get("/api/v1/admin/organizations")).json()
    atelier = next(o for o in orgs if o["name"] == "Atelier Test")
    assert atelier["members"] == 2 and atelier["clients"] == 1
    assert set(atelier) == {
        "id",
        "name",
        "slug",
        "status",
        "created_at",
        "require_2fa",
        "members",
        "clients",
        "support_until",
    }  # names and counts only

    created = await send(
        admin,
        "POST",
        "/api/v1/admin/organizations",
        json={"name": "Neue Agentur", "admin_email": "new@example.com"},
    )
    assert created.status_code == 201
    assert "/invite/" in created.json()["invitation_link"]

    suspended = await send(admin, "POST", f"/api/v1/admin/organizations/{world.org_a}/suspend")
    assert suspended.json()["status"] == "suspended"
    members = await world["member"].client.get(f"/api/v1/orgs/{world.org_a}/members")
    assert members.status_code == 404
    await send(admin, "POST", f"/api/v1/admin/organizations/{world.org_a}/reactivate")
    assert (
        await world["member"].client.get(f"/api/v1/orgs/{world.org_a}/members")
    ).status_code == 200
    log = (await world["org_admin"].client.get(f"/api/v1/orgs/{world.org_a}/audit-log")).json()
    actions = [e["action"] for e in log["items"]]
    assert "admin.organization_suspended" in actions


async def test_support_view_needs_a_grant(world: World, admin: AsyncClient) -> None:
    path = f"/api/v1/admin/organizations/{world.org_a}/support"
    org_admin = world["org_admin"].client
    grants = f"/api/v1/orgs/{world.org_a}/support-access"

    denied = await admin.get(path)
    assert denied.status_code == 403
    assert denied.json()["code"] == "no_support_access"
    assert (await send(world["member"].client, "POST", grants, json={})).status_code == 403

    granted = await send(org_admin, "POST", grants, json={"days": 2, "reason": "Login problem"})
    assert granted.status_code == 201
    view = await admin.get(path)
    assert view.status_code == 200, view.text
    body = view.json()
    assert {m["email"] for m in body["members"]} >= {"admin@example.com", "member@example.com"}
    assert body["audit"][0]["action"] == "support.viewed"

    await send(org_admin, "DELETE", f"{grants}/{granted.json()['id']}")
    assert (await admin.get(path)).status_code == 403
    listed = (await org_admin.get(grants)).json()
    assert listed[0]["active"] is False and listed[0]["revoked_at"] is not None


async def test_support_view_cannot_write(
    world: World, admin: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The support transaction is read-only even if code tried to change something."""
    from app.admin import service

    await send(
        world["org_admin"].client, "POST", f"/api/v1/orgs/{world.org_a}/support-access", json={}
    )

    async def write_attempt(db, admin_, org_id):  # type: ignore[no-untyped-def]
        await original_view(db, admin_, org_id)
        await db.execute(text("UPDATE organizations SET name = 'hacked'"))

    original_view = service.support_view
    monkeypatch.setattr(service, "support_view", write_attempt)
    with pytest.raises(Exception, match="read-only transaction"):
        await admin.get(f"/api/v1/admin/organizations/{world.org_a}/support")


async def test_reset_two_factor_for_a_locked_out_member(world: World, admin: AsyncClient) -> None:
    await turn_on(world["member"].client)
    body = {"email": "member@example.com", "reason": "Lost phone and codes"}

    denied = await send(admin, "POST", "/api/v1/admin/users/reset-2fa", json=body)
    assert denied.status_code == 403
    assert denied.json()["code"] == "no_support_access"
    await reauth(world["org_admin"].client)
    await send(
        world["org_admin"].client, "POST", f"/api/v1/orgs/{world.org_a}/support-access", json={}
    )
    ok = await send(admin, "POST", "/api/v1/admin/users/reset-2fa", json=body)

    assert ok.status_code == 204, ok.text
    assert (await world["member"].client.get("/api/v1/me")).json()["two_factor_enabled"] is False


async def test_two_factor_of_another_platform_admin_cannot_be_reset(
    world: World, admin: AsyncClient, owner_engine: AsyncEngine
) -> None:
    await make_admin(owner_engine, "member@example.com")
    await turn_on(world["member"].client)

    response = await send(
        admin,
        "POST",
        "/api/v1/admin/users/reset-2fa",
        json={"email": "member@example.com", "reason": "Says they lost the phone"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "not_allowed"
    assert (await world["member"].client.get("/api/v1/me")).json()["two_factor_enabled"] is True
