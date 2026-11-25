from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import new_client
from tests.helpers import World, accept, last_email_to, send, token_from_link
from tests.test_tasks import P, new_task
from tests.test_tasks import wedding as wedding
from tests.test_tasks import world as world

COUPLE = "couple@example.com"


@pytest.fixture
async def couple(app: FastAPI, world: World, wedding: dict[str, Any]) -> AsyncClient:
    response = await send(
        world["member"].client,
        "POST",
        P(world, wedding, "/client-access/invitations"),
        json={"email": COUPLE},
    )
    assert response.status_code == 201, response.text
    return await accept(app, token_from_link(last_email_to(COUPLE), "invite"), "Mia Becker")


async def budget(client: AsyncClient, world: World, wedding: dict[str, Any]) -> Any:
    response = await client.get(P(world, wedding, "/budget"))
    assert response.status_code == 200, response.text
    return response.json()


async def add_item(
    client: AsyncClient, world: World, wedding: dict[str, Any], category: str, **body: Any
) -> Any:
    current = await budget(client, world, wedding)
    category_id = next(c["id"] for c in current["categories"] if c["name"] == category)
    response = await send(
        client,
        "POST",
        P(world, wedding, "/budget/items"),
        json={"category_id": category_id, "title": category, **body},
    )
    assert response.status_code == 201, response.text
    return response.json()


def item_named(view: Any, title: str) -> Any:
    return next(i for c in view["categories"] for i in c["items"] if i["title"] == title)


def all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in all_keys(v)}
    return set()


# --- Budget (planner side) -----------------------------------------------------------------


async def test_new_weddings_get_default_budget_categories(
    world: World, wedding: dict[str, Any]
) -> None:
    view = await budget(world["member"].client, world, wedding)

    assert [c["name"] for c in view["categories"]][:3] == ["Venue", "Catering", "Photography"]
    assert view["totals"]["planned_cents"] == 0
    assert view["warnings"] == []


async def test_totals_forecast_and_warnings(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    view = await budget(lead, world, wedding)
    frame = await send(
        lead,
        "PATCH",
        P(world, wedding, "/budget"),
        json={"total_cents": 38_000_00},
        headers={"If-Match": f'"{view["version"]}"'},
    )
    await add_item(
        lead, world, wedding, "Venue", planned_cents=12_500_00, contracted_cents=12_500_00
    )
    await add_item(
        lead,
        world,
        wedding,
        "Catering",
        planned_cents=9_800_00,
        quoted_cents=9_200_00,
        internal_cost_cents=8_300_00,
    )
    view = await add_item(
        lead, world, wedding, "Flowers & Decor", planned_cents=2_900_00, quoted_cents=3_400_00
    )

    assert frame.status_code == 200
    assert view["totals"] == {
        "planned_cents": 25_200_00,
        "quoted_cents": 12_600_00,
        "contracted_cents": 12_500_00,
        "paid_cents": 0,
        "forecast_cents": 25_100_00,
        "internal_cost_cents": 8_300_00,
        "unplanned_cents": 12_800_00,
    }
    assert [(w["code"], w["amount_cents"]) for w in view["warnings"]] == [
        ("quote_above_plan", 500_00)
    ]

    over = await add_item(lead, world, wedding, "Music", planned_cents=14_000_00)
    assert over["warnings"][0] == {
        "code": "over_budget",
        "amount_cents": 1_100_00,
        "item_id": None,
        "title": None,
    }


async def test_payments_and_overdue_warning(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    view = await add_item(
        lead, world, wedding, "Venue", planned_cents=10_000_00, contracted_cents=10_000_00
    )
    item = item_named(view, "Venue")
    base = P(world, wedding, f"/budget/items/{item['id']}/payments")

    await send(
        lead, "POST", base, json={"label": "Deposit", "amount_cents": 4_000_00, "paid": True}
    )
    view = (
        await send(
            lead,
            "POST",
            base,
            json={"label": "Rest", "amount_cents": 6_000_00, "due_date": "2026-01-01"},
        )
    ).json()
    rest = view["upcoming_payments"][0]

    assert view["totals"]["paid_cents"] == 4_000_00
    assert rest["overdue"] is True
    assert view["warnings"][-1]["code"] == "payment_overdue"
    paid = (await send(lead, "PATCH", f"{base}/{rest['id']}", json={"paid": True})).json()
    assert paid["totals"]["paid_cents"] == 10_000_00
    assert paid["upcoming_payments"] == []


async def test_budget_permissions_and_versions(world: World, wedding: dict[str, Any]) -> None:
    viewer = world["member2"].client
    view = await add_item(world["member"].client, world, wedding, "Venue", planned_cents=100_00)
    item = item_named(view, "Venue")

    read = await viewer.get(P(world, wedding, "/budget"))
    write = await send(
        viewer, "POST", P(world, wedding, "/budget/categories"), json={"name": "Extras"}
    )
    frame = await send(viewer, "PATCH", P(world, wedding, "/budget"), json={"total_cents": 1})
    stale = await send(
        world["member"].client,
        "PATCH",
        P(world, wedding, f"/budget/items/{item['id']}"),
        json={"planned_cents": 200_00},
        headers={"If-Match": '"7"'},
    )

    assert read.status_code == 200
    assert write.status_code == 403
    assert frame.status_code == 403
    assert stale.status_code == 412


# --- Couple access ---------------------------------------------------------------------------


async def test_couple_invitation_opens_the_portal(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    me = (await couple.get("/api/v1/me")).json()
    projects = (await couple.get("/api/v1/portal/projects")).json()
    access = (await world["member"].client.get(P(world, wedding, "/client-access"))).json()

    assert [m["role"] for m in me["memberships"]] == ["client"]
    assert [(p["id"], p["organization"]["name"]) for p in projects] == [
        (wedding["id"], "Atelier Test")
    ]
    assert [login["email"] for login in access["logins"]] == [COUPLE]
    assert access["invitations"] == []


async def test_team_members_cannot_be_invited_as_the_couple(
    world: World, wedding: dict[str, Any]
) -> None:
    response = await send(
        world["member"].client,
        "POST",
        P(world, wedding, "/client-access/invitations"),
        json={"email": "member2@example.com"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "team_member"


async def test_portal_shows_only_what_is_shared(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    await new_task(lead, world, wedding, title="Secret supplier haggling")
    await add_item(
        lead,
        world,
        wedding,
        "Venue",
        planned_cents=12_500_00,
        internal_cost_cents=9_000_00,
        visibility="client",
        notes_internal="Margin 20 %",
    )
    await add_item(lead, world, wedding, "Contingency", planned_cents=1_200_00)
    K = f"/api/v1/portal/projects/{wedding['id']}"

    overview = (await couple.get(K)).json()
    tasks = (await couple.get(f"{K}/tasks")).json()
    portal_budget = (await couple.get(f"{K}/budget")).json()

    planner_tasks = (await lead.get(P(world, wedding, "/tasks"))).json()
    shared = [t for t in planner_tasks if t["visibility"] == "client"]
    assert len(tasks) == len(shared) < len(planner_tasks)
    assert "Secret supplier haggling" not in {t["title"] for t in tasks}
    assert all(t["for_couple"] for t in overview["next_steps"])
    assert [m["full_name"] for m in overview["team"]] == ["Max Member"]
    assert [c["name"] for c in portal_budget["categories"]] == ["Venue"]
    keys = all_keys(overview) | all_keys(tasks) | all_keys(portal_budget)
    assert not keys & {
        "internal_cost_cents",
        "notes_internal",
        "assignee_membership_id",
        "visibility",
    }


async def test_couple_completes_only_their_own_tasks(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    K = f"/api/v1/portal/projects/{wedding['id']}"
    tasks = (await couple.get(f"{K}/tasks")).json()
    theirs = next(t for t in tasks if t["for_couple"])
    team_task = next(t for t in tasks if not t["for_couple"])
    internal = await new_task(lead, world, wedding, title="Internal only")

    done = await send(couple, "POST", f"{K}/tasks/{theirs['id']}/complete")
    blocked = await send(couple, "POST", f"{K}/tasks/{team_task['id']}/complete")
    hidden = await send(couple, "POST", f"{K}/tasks/{internal['id']}/complete")
    feed = (await lead.get(P(world, wedding, "/activity"))).json()["items"]

    assert next(t for t in done.json() if t["id"] == theirs["id"])["status"] == "done"
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "not_your_task"
    assert hidden.status_code == 404
    assert feed[0]["verb"] == "task.completed"
    assert feed[0]["actor_name"] == "Mia Becker"


async def test_couple_comments_reach_the_planner(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    K = f"/api/v1/portal/projects/{wedding['id']}"
    task = next(t for t in (await couple.get(f"{K}/tasks")).json() if t["for_couple"])

    posted = await send(
        couple, "POST", f"{K}/tasks/{task['id']}/comments", json={"body": "Done by Friday!"}
    )
    seen = (
        await world["member"].client.get(
            P(world, wedding, "/comments"), params={"target_type": "task", "target_id": task["id"]}
        )
    ).json()

    own = (await couple.get(f"{K}/tasks/{task['id']}/comments")).json()

    assert posted.status_code == 201
    assert [c["body"] for c in own] == ["Done by Friday!"]
    assert [(c["author_name"], c["visibility"]) for c in seen] == [("Mia Becker", "client")]


async def test_couples_cannot_use_the_planner_api(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    assert (await couple.get(P(world, wedding))).status_code == 403
    assert (await couple.get(P(world, wedding, "/tasks"))).status_code == 403
    assert (await couple.get(P(world, wedding, "/budget"))).status_code == 403
    assert (await couple.get(f"/api/v1/orgs/{world.org_a}/members")).status_code == 403


async def test_other_couples_and_outsiders_cannot_open_the_portal(
    app: FastAPI, world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    K = f"/api/v1/portal/projects/{wedding['id']}"

    assert (await world["client"].client.get(K)).status_code == 404
    assert (await world["outsider"].client.get(K)).status_code == 404
    assert (await new_client(app).get(K)).status_code == 401


async def test_revoking_access_closes_the_portal(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    access = (await world["member"].client.get(P(world, wedding, "/client-access"))).json()
    login = access["logins"][0]

    revoked = await send(
        world["member"].client,
        "DELETE",
        P(world, wedding, f"/client-access/{login['project_member_id']}"),
    )

    assert revoked.status_code == 204
    assert (await couple.get(f"/api/v1/portal/projects/{wedding['id']}")).status_code == 404
    assert (await couple.get("/api/v1/me")).json()["memberships"] == []


async def test_client_rls_in_sql(
    world: World, wedding: dict[str, Any], couple: AsyncClient, app_engine: AsyncEngine
) -> None:
    lead = world["member"].client
    await new_task(lead, world, wedding, title="Internal")
    await add_item(lead, world, wedding, "Venue", planned_cents=1, visibility="client")
    await add_item(lead, world, wedding, "Music", planned_cents=1)
    couple_id = (await couple.get("/api/v1/me")).json()["id"]

    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true), "
                "set_config('app.role', 'client', true)"
            ),
            {"o": str(world.org_a), "u": couple_id},
        )

        async def count(sql: str) -> int:
            return int((await conn.execute(text(sql))).scalar_one())

        assert await count("SELECT count(*) FROM tasks WHERE visibility = 'internal'") == 0
        assert await count("SELECT count(*) FROM tasks") > 0
        assert await count("SELECT count(*) FROM budget_items") == 1
        # Only their own audit entries (for their data export), nothing else of the log.
        assert (
            await count(
                f"SELECT count(*) FROM audit_log WHERE actor_user_id IS DISTINCT FROM '{couple_id}'"
            )
            == 0
        )
        assert await count("SELECT count(*) FROM invitations") == 0
        assert await count("SELECT count(*) FROM project_vendors") == 0
        # Own membership plus the wedding team (lead + viewer), not the rest of the org.
        assert await count("SELECT count(*) FROM memberships") == 3


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_revoking_a_pending_couple_invitation_voids_the_link(
    app: FastAPI, world: World, wedding: dict[str, Any]
) -> None:
    lead = world["member"].client
    invited = await send(
        lead, "POST", P(world, wedding, "/client-access/invitations"), json={"email": COUPLE}
    )
    invitation = invited.json()["invitations"][0]
    token = token_from_link(last_email_to(COUPLE), "invite")

    revoked = await send(
        lead, "DELETE", P(world, wedding, f"/client-access/invitations/{invitation['id']}")
    )
    access = (await lead.get(P(world, wedding, "/client-access"))).json()
    link = await new_client(app).get(f"/api/v1/auth/invitations/{token}")

    assert revoked.status_code == 204
    assert access["invitations"] == []
    assert link.status_code == 404
    assert link.json()["code"] == "invitation_invalid"


async def test_only_leads_and_admins_manage_couple_access(
    world: World, wedding: dict[str, Any]
) -> None:
    viewer = world["member2"].client

    listed = await viewer.get(P(world, wedding, "/client-access"))
    invited = await send(
        viewer, "POST", P(world, wedding, "/client-access/invitations"), json={"email": COUPLE}
    )
    admin = await world["org_admin"].client.get(P(world, wedding, "/client-access"))

    assert listed.status_code == 403
    assert invited.status_code == 403
    assert admin.status_code == 200
    assert admin.json() == {"logins": [], "invitations": []}


async def test_couple_ticks_checklist_items_and_reopens_their_task(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    task = await new_task(
        lead,
        world,
        wedding,
        title="Choose the menu",
        visibility="client",
        assignee_type="client",
        checklist=["Taste starters", "Pick dessert"],
    )
    K = f"/api/v1/portal/projects/{wedding['id']}"
    item = task["checklist"][0]

    ticked = await send(
        couple, "PATCH", f"{K}/tasks/{task['id']}/checklist/{item['id']}", json={"is_done": True}
    )
    await send(couple, "POST", f"{K}/tasks/{task['id']}/complete")
    reopened = await send(couple, "POST", f"{K}/tasks/{task['id']}/reopen")
    planner_view = (await lead.get(P(world, wedding, f"/tasks/{task['id']}"))).json()

    mine = next(t for t in ticked.json() if t["id"] == task["id"])
    assert [i["is_done"] for i in mine["checklist"]] == [True, False]
    assert next(t for t in reopened.json() if t["id"] == task["id"])["status"] != "done"
    assert planner_view["checklist_done"] == 1
