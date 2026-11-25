import pytest
from fastapi import FastAPI

from app.organizations.models import OrgRole
from tests.helpers import Member, World, accept, build_world, invite_directly, send


@pytest.fixture
async def world(app: FastAPI) -> World:
    world = await build_world(app)
    token = await invite_directly(world.org_a, "member2@example.com", OrgRole.MEMBER)
    world.users["member2"] = Member(await accept(app, token, "Mira Second"), "member2@example.com")
    return world


def url(world: World, path: str) -> str:
    return f"/api/v1/orgs/{world.org_a}{path}"


async def test_client_with_contacts(world: World) -> None:
    client = world["member"].client
    created = await send(
        client,
        "POST",
        url(world, "/clients"),
        json={
            "display_name": "Anna & Lukas",
            "status": "proposal",
            "contacts": [
                {"first_name": "Anna", "last_name": "Beispiel", "email": "anna@example.com"},
                {"first_name": "Lukas", "email": "lukas@example.com"},
            ],
        },
    )
    body = created.json()
    listed = (await client.get(url(world, "/clients"), params={"q": "anna"})).json()

    assert created.status_code == 201
    assert [c["is_primary"] for c in body["contacts"]] == [True, False]
    assert listed[0]["primary_contact"] == "Anna Beispiel"
    assert listed[0]["primary_email"] == "anna@example.com"


async def test_clients_are_private_to_their_creator_until_linked(world: World) -> None:
    created = (
        await send(
            world["member"].client, "POST", url(world, "/clients"), json={"display_name": "X & Y"}
        )
    ).json()
    path = url(world, f"/clients/{created['id']}")

    assert (await world["member2"].client.get(path)).status_code == 404
    assert (await world["org_admin"].client.get(path)).status_code == 200


async def test_clients_with_weddings_cannot_be_deleted(world: World) -> None:
    admin = world["org_admin"].client
    wedding = (
        await send(admin, "POST", url(world, "/projects"), json={"new_client_name": "C & D"})
    ).json()
    path = url(world, f"/clients/{wedding['client_id']}")

    member_delete = await send(world["member"].client, "DELETE", path)
    blocked = await send(admin, "DELETE", path)

    assert member_delete.status_code == 403
    assert blocked.status_code == 409


async def test_vendor_directory(world: World) -> None:
    client = world["member"].client
    created = await send(
        client,
        "POST",
        url(world, "/vendors"),
        json={
            "name": "Studio Licht",
            "category": "photo",
            "website": "https://example.com",
            "rating": 5,
        },
    )
    invalid = await send(
        client, "POST", url(world, "/vendors"), json={"name": "X", "category": "unknown"}
    )
    photo = (await client.get(url(world, "/vendors"), params={"category": "photo"})).json()
    deleted = await send(client, "DELETE", url(world, f"/vendors/{created.json()['id']}"))

    assert created.status_code == 201
    assert invalid.status_code == 422
    assert [v["name"] for v in photo] == ["Studio Licht"]
    assert deleted.status_code == 204
    assert (await client.get(url(world, "/vendors"))).json() == []


async def test_templates_are_read_by_planners_and_managed_by_admins(world: World) -> None:
    admin, member = world["org_admin"].client, world["member"].client
    templates = (await member.get(url(world, "/templates"))).json()
    default = templates[0]

    member_create = await send(member, "POST", url(world, "/templates"), json={"name": "Mine"})
    copy = await send(
        admin,
        "POST",
        url(world, "/templates"),
        json={"name": "Elopement", "copy_from": default["id"]},
    )

    assert default["is_default"] is True
    assert (default["milestone_count"], default["task_count"]) == (6, 19)
    assert member_create.status_code == 403
    assert copy.status_code == 201
    assert (copy.json()["milestone_count"], copy.json()["task_count"]) == (6, 19)
    parents = {i["id"] for i in copy.json()["items"] if i["kind"] == "milestone"}
    assert all(i["parent_item_id"] in parents for i in copy.json()["items"] if i["kind"] == "task")


async def test_template_tasks_must_belong_to_a_milestone_of_the_same_template(world: World) -> None:
    admin = world["org_admin"].client
    first = (await send(admin, "POST", url(world, "/templates"), json={"name": "A"})).json()
    second = (await send(admin, "POST", url(world, "/templates"), json={"name": "B"})).json()
    milestone = (
        await send(
            admin,
            "POST",
            url(world, f"/templates/{first['id']}/items"),
            json={"kind": "milestone", "title": "M", "offset_days": -30},
        )
    ).json()

    response = await send(
        admin,
        "POST",
        url(world, f"/templates/{second['id']}/items"),
        json={"kind": "task", "title": "T", "offset_days": -40, "parent_item_id": milestone["id"]},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_parent"


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_templates_are_edited_made_default_and_deleted(world: World) -> None:
    admin = world["org_admin"].client
    template = (
        await send(admin, "POST", url(world, "/templates"), json={"name": "Small wedding"})
    ).json()
    base = url(world, f"/templates/{template['id']}")
    milestone = (
        await send(
            admin,
            "POST",
            f"{base}/items",
            json={"kind": "milestone", "title": "Venue", "offset_days": -180},
        )
    ).json()

    renamed_item = await send(
        admin, "PATCH", f"{base}/items/{milestone['id']}", json={"offset_days": -200}
    )
    default = await send(admin, "PATCH", base, json={"name": "Intimate", "is_default": True})
    listed = (await admin.get(url(world, "/templates"))).json()
    removed_item = await send(admin, "DELETE", f"{base}/items/{milestone['id']}")
    after_item = (await admin.get(base)).json()
    deleted = await send(admin, "DELETE", base)

    assert renamed_item.json()["offset_days"] == -200
    assert default.json()["name"] == "Intimate"
    assert [t["name"] for t in listed if t["is_default"]] == ["Intimate"]
    assert removed_item.status_code == 204
    assert after_item["items"] == []
    assert deleted.status_code == 204
    assert (await admin.get(base)).status_code == 404
