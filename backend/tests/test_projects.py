from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.organizations.models import OrgRole
from tests.helpers import Member, World, accept, build_world, invite_directly, send


@pytest.fixture
async def world(app: FastAPI) -> World:
    world = await build_world(app)
    token = await invite_directly(world.org_a, "member2@example.com", OrgRole.MEMBER)
    world.users["member2"] = Member(await accept(app, token, "Mira Second"), "member2@example.com")
    members = (await world["org_admin"].client.get(f"/api/v1/orgs/{world.org_a}/members")).json()
    for m in members:
        if m["email"] == "member2@example.com":
            world.users["member2"].membership_id = m["id"]
    return world


def url(world: World, path: str = "") -> str:
    return f"/api/v1/orgs/{world.org_a}{path}"


async def create_wedding(
    client: AsyncClient, world: World, days_ahead: int | None = 200, **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"new_client_name": "Mia & Tom", "venue_name": "Gut Lindenhof", **extra}
    if days_ahead is not None:
        body["wedding_date"] = (date.today() + timedelta(days=days_ahead)).isoformat()
    response = await send(client, "POST", url(world, "/projects"), json=body)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_new_wedding_uses_the_default_template(world: World) -> None:
    wedding = await create_wedding(world["org_admin"].client, world, days_ahead=400)

    assert wedding["title"] == "Mia & Tom"
    assert wedding["client_name"] == "Mia & Tom"
    assert wedding["milestones"][0]["title"] == "Venue and date secured"
    assert len(wedding["milestones"]) == 6
    assert wedding["progress"] == {"done": 0, "total": 19, "percent": 0}
    assert wedding["milestones"][-1]["due_date"] == (date.today() + timedelta(days=400)).isoformat()
    assert [t["full_name"] for t in wedding["team"]] == ["Ada Admin"]
    assert wedding["team"][0]["project_role"] == "lead"


async def test_weddings_are_visible_only_to_their_team(world: World) -> None:
    wedding = await create_wedding(world["member"].client, world)
    path = url(world, f"/projects/{wedding['id']}")

    assert (await world["member"].client.get(path)).status_code == 200
    assert (await world["org_admin"].client.get(path)).status_code == 200
    assert (await world["member2"].client.get(path)).status_code == 404
    assert (await world["outsider"].client.get(path)).status_code == 404
    listed = (await world["member2"].client.get(url(world, "/projects"))).json()
    assert listed == []


async def test_assigning_a_planner_grants_access(world: World) -> None:
    wedding = await create_wedding(world["member"].client, world)
    base = url(world, f"/projects/{wedding['id']}")

    added = await send(
        world["member"].client,
        "POST",
        f"{base}/members",
        json={"membership_id": str(world["member2"].membership_id), "project_role": "viewer"},
    )
    as_viewer = await world["member2"].client.get(base)
    viewer_edit = await send(
        world["member2"].client,
        "PATCH",
        base,
        json={"title": "Nope"},
        headers={"If-Match": f'"{as_viewer.json()["version"]}"'},
    )

    assert added.status_code == 201
    assert as_viewer.status_code == 200
    assert as_viewer.json()["my_role"] == "viewer"
    assert viewer_edit.status_code == 403


async def test_updates_need_the_current_version(world: World) -> None:
    client = world["org_admin"].client
    wedding = await create_wedding(client, world)
    base = url(world, f"/projects/{wedding['id']}")

    missing = await send(client, "PATCH", base, json={"guest_count_planned": 120})
    ok = await send(
        client, "PATCH", base, json={"guest_count_planned": 120}, headers={"If-Match": '"1"'}
    )
    stale = await send(
        client, "PATCH", base, json={"guest_count_planned": 90}, headers={"If-Match": '"1"'}
    )

    assert missing.status_code == 428
    assert missing.json()["code"] == "precondition_required"
    assert ok.status_code == 200
    assert ok.headers["etag"] == '"2"'
    assert ok.json()["guest_count_planned"] == 120
    assert stale.status_code == 412
    assert stale.json()["code"] == "stale_version"


async def test_every_wedding_keeps_a_lead(world: World) -> None:
    client = world["org_admin"].client
    wedding = await create_wedding(client, world)
    lead = wedding["team"][0]

    response = await send(
        client,
        "PATCH",
        url(world, f"/projects/{wedding['id']}/members/{lead['id']}"),
        json={"project_role": "planner"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "last_lead"


async def test_only_admins_delete_and_archived_weddings_leave_the_list(world: World) -> None:
    wedding = await create_wedding(world["member"].client, world)
    base = url(world, f"/projects/{wedding['id']}")

    lead_delete = await send(world["member"].client, "DELETE", base)
    archived = await send(world["member"].client, "POST", f"{base}/archive")
    default_list = (await world["member"].client.get(url(world, "/projects"))).json()
    archived_list = (
        await world["member"].client.get(url(world, "/projects"), params={"status": "archived"})
    ).json()
    admin_delete = await send(world["org_admin"].client, "DELETE", base)

    assert lead_delete.status_code == 403
    assert archived.json()["status"] == "archived"
    assert default_list == []
    assert [w["id"] for w in archived_list] == [wedding["id"]]
    assert admin_delete.status_code == 204
    assert (await world["org_admin"].client.get(base)).status_code == 404


async def test_client_logins_cannot_use_the_planner_api(world: World) -> None:
    client = world["client"].client

    assert (await client.get(url(world, "/projects"))).status_code == 403
    assert (await client.get(url(world, "/clients"))).status_code == 403
    assert (await client.get(url(world, "/vendors"))).status_code == 403
    assert (await client.get(url(world, "/dashboard"))).status_code == 403


async def test_dashboard_counts_overdue_and_upcoming(world: World) -> None:
    await create_wedding(world["org_admin"].client, world, days_ahead=120)

    board = (await world["org_admin"].client.get(url(world, "/dashboard"))).json()

    assert board["active_weddings"] == 1
    assert board["weddings_next_6_months"] == 1
    assert board["overdue_tasks"] > 0  # template tasks due more than 120 days before
    assert board["overdue_weddings"] == 1
    assert [w["days_to_go"] for w in board["upcoming"]] == [120]


async def test_wedding_vendors(world: World) -> None:
    client = world["org_admin"].client
    vendor = (
        await send(
            client,
            "POST",
            url(world, "/vendors"),
            json={"name": "Blumenwerk", "category": "flowers"},
        )
    ).json()
    wedding = await create_wedding(client, world)
    base = url(world, f"/projects/{wedding['id']}/vendors")

    linked = await send(client, "POST", base, json={"vendor_id": vendor["id"]})
    again = await send(client, "POST", base, json={"vendor_id": vendor["id"]})
    booked = await send(client, "PATCH", f"{base}/{linked.json()['id']}", json={"status": "booked"})

    assert linked.status_code == 201
    assert again.status_code == 409
    assert again.json()["code"] == "already_linked"
    assert booked.json()["status"] == "booked"
    assert (await client.get(url(world, f"/vendors/{vendor['id']}"))).json()["project_count"] == 1


async def test_rls_hides_unassigned_weddings_in_sql(world: World, app_engine: AsyncEngine) -> None:
    await create_wedding(world["member"].client, world)
    member2_user = (await world["member2"].client.get("/api/v1/me")).json()["id"]

    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true), "
                "set_config('app.role', 'member', true)"
            ),
            {"o": str(world.org_a), "u": member2_user},
        )
        projects = (await conn.execute(text("SELECT count(*) FROM projects"))).scalar_one()
        tasks = (await conn.execute(text("SELECT count(*) FROM tasks"))).scalar_one()
        clients = (await conn.execute(text("SELECT count(*) FROM clients"))).scalar_one()

    assert (projects, tasks, clients) == (0, 0, 0)


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_restoring_an_archived_wedding(world: World) -> None:
    client = world["member"].client
    upcoming = await create_wedding(client, world, days_ahead=120)
    past = await create_wedding(client, world, days_ahead=-10)
    for wedding in (upcoming, past):
        await send(client, "POST", url(world, f"/projects/{wedding['id']}/archive"))

    restored_upcoming = await send(
        client, "POST", url(world, f"/projects/{upcoming['id']}/restore")
    )
    restored_past = await send(client, "POST", url(world, f"/projects/{past['id']}/restore"))
    listed = (await client.get(url(world, "/projects"))).json()

    # The status follows the wedding date: still ahead means planning, passed means completed.
    assert restored_upcoming.json()["status"] == "planning"
    assert restored_past.json()["status"] == "completed"
    assert {w["id"] for w in listed} == {upcoming["id"], past["id"]}


async def test_milestones_are_added_changed_and_removed(world: World) -> None:
    client = world["member"].client
    wedding = await create_wedding(client, world)
    base = url(world, f"/projects/{wedding['id']}/milestones")

    added = await send(
        client, "POST", base, json={"title": "Rehearsal dinner", "due_date": "2027-06-11"}
    )
    new = next(m for m in added.json() if m["title"] == "Rehearsal dinner")
    renamed = await send(client, "PATCH", f"{base}/{new['id']}", json={"title": "Welcome dinner"})
    first = renamed.json()[0]
    tasks = (
        await client.get(
            url(world, f"/projects/{wedding['id']}/tasks"), params={"milestone_id": first["id"]}
        )
    ).json()
    removed = await send(client, "DELETE", f"{base}/{first['id']}")
    after = (await client.get(base)).json()
    all_tasks = (await client.get(url(world, f"/projects/{wedding['id']}/tasks"))).json()

    assert added.status_code == 201 and len(added.json()) == 7
    assert "Welcome dinner" in [m["title"] for m in renamed.json()]
    assert removed.status_code == 204
    assert first["id"] not in [m["id"] for m in after] and len(after) == 6
    assert len(all_tasks) == 19  # tasks of a removed milestone stay, without milestone
    assert {t["id"] for t in tasks} <= {t["id"] for t in all_tasks if t["milestone_id"] is None}


async def test_wedding_team_roles_change_and_members_leave(world: World) -> None:
    lead = world["member"].client
    wedding = await create_wedding(lead, world)
    base = url(world, f"/projects/{wedding['id']}")
    added = await send(
        lead,
        "POST",
        f"{base}/members",
        json={"membership_id": str(world["member2"].membership_id), "project_role": "planner"},
    )
    again = await send(
        lead,
        "POST",
        f"{base}/members",
        json={"membership_id": str(world["member2"].membership_id)},
    )
    entry = next(m for m in added.json() if m["full_name"] == "Mira Second")

    changed = await send(
        lead, "PATCH", f"{base}/members/{entry['id']}", json={"project_role": "viewer"}
    )
    as_viewer = (await world["member2"].client.get(base)).json()
    removed = await send(lead, "DELETE", f"{base}/members/{entry['id']}")

    assert again.json()["code"] == "already_assigned"
    assert changed.status_code == 200
    assert as_viewer["my_role"] == "viewer"
    assert removed.status_code == 204
    assert (await world["member2"].client.get(base)).status_code == 404
    team = (await lead.get(f"{base}/members")).json()
    assert [m["full_name"] for m in team] == ["Max Member"]


async def test_a_vendor_is_removed_from_a_wedding(world: World) -> None:
    client = world["member"].client
    vendor = (
        await send(
            client, "POST", url(world, "/vendors"), json={"name": "DJ Nord", "category": "music"}
        )
    ).json()
    wedding = await create_wedding(client, world)
    base = url(world, f"/projects/{wedding['id']}/vendors")
    link = (await send(client, "POST", base, json={"vendor_id": vendor["id"]})).json()

    listed = (await client.get(base)).json()
    removed = await send(client, "DELETE", f"{base}/{link['id']}")

    assert [v["name"] for v in listed] == ["DJ Nord"]
    assert removed.status_code == 204
    assert (await client.get(base)).json() == []
    assert (await client.get(url(world, f"/vendors/{vendor['id']}"))).json()["project_count"] == 0
