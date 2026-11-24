from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.organizations.models import OrgRole
from tests.helpers import Member, World, accept, build_world, invite_directly, send
from tests.test_projects import create_wedding


@pytest.fixture
async def world(app: FastAPI) -> World:
    world = await build_world(app)
    token = await invite_directly(world.org_a, "member2@example.com", OrgRole.MEMBER)
    world.users["member2"] = Member(await accept(app, token, "Mira Second"), "member2@example.com")
    members = (await world["org_admin"].client.get(f"/api/v1/orgs/{world.org_a}/members")).json()
    for m in members:
        for user in world.users.values():
            if user.email == m["email"]:
                user.membership_id = m["id"]
    return world


@pytest.fixture
async def wedding(world: World) -> dict[str, Any]:
    """A wedding led by `member`, with `member2` as viewer."""
    wedding = await create_wedding(world["member"].client, world, days_ahead=300)
    await send(
        world["member"].client,
        "POST",
        f"/api/v1/orgs/{world.org_a}/projects/{wedding['id']}/members",
        json={"membership_id": str(world["member2"].membership_id), "project_role": "viewer"},
    )
    return wedding


def P(world: World, wedding: dict[str, Any], path: str = "") -> str:
    return f"/api/v1/orgs/{world.org_a}/projects/{wedding['id']}{path}"


async def new_task(client: AsyncClient, world: World, wedding: dict[str, Any], **body: Any) -> Any:
    response = await send(
        client, "POST", P(world, wedding, "/tasks"), json={"title": "Book a band", **body}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_template_tasks_are_listed_with_milestones(
    world: World, wedding: dict[str, Any]
) -> None:
    tasks = (await world["member"].client.get(P(world, wedding, "/tasks"))).json()
    shared = (
        await world["member"].client.get(
            P(world, wedding, "/tasks"), params={"visibility": "client"}
        )
    ).json()

    assert len(tasks) == 19
    assert all(t["milestone_title"] for t in tasks)
    assert 0 < len(shared) < 19
    assert all(t["visibility"] == "client" for t in shared)


async def test_create_task_with_checklist_and_assignee(
    world: World, wedding: dict[str, Any]
) -> None:
    milestone = (await world["member"].client.get(P(world, wedding, "/milestones"))).json()[0]

    task = await new_task(
        world["member"].client,
        world,
        wedding,
        milestone_id=milestone["id"],
        due_date="2027-01-15",
        priority="high",
        assignee_membership_id=str(world["member"].membership_id),
        checklist=["Shortlist three bands", "Listen to demos"],
    )

    assert task["milestone_title"] == milestone["title"]
    assert task["assignee_name"] == "Max Member"
    assert [i["title"] for i in task["checklist"]] == ["Shortlist three bands", "Listen to demos"]
    assert (task["checklist_total"], task["checklist_done"]) == (2, 0)


async def test_assignee_must_be_on_the_wedding(world: World, wedding: dict[str, Any]) -> None:
    outsider_of_wedding = await send(
        world["member"].client,
        "POST",
        P(world, wedding, "/tasks"),
        json={"title": "X", "assignee_membership_id": str(world["client"].membership_id)},
    )
    admin_can_be_assigned = await send(
        world["member"].client,
        "POST",
        P(world, wedding, "/tasks"),
        json={"title": "Y", "assignee_membership_id": str(world["org_admin"].membership_id)},
    )

    assert outsider_of_wedding.status_code == 422
    assert outsider_of_wedding.json()["code"] == "invalid_assignee"
    assert admin_can_be_assigned.status_code == 201


async def test_viewers_read_and_comment_but_do_not_edit(
    world: World, wedding: dict[str, Any]
) -> None:
    task = await new_task(world["member"].client, world, wedding)
    viewer = world["member2"].client

    read = await viewer.get(P(world, wedding, f"/tasks/{task['id']}"))
    create = await send(viewer, "POST", P(world, wedding, "/tasks"), json={"title": "Nope"})
    complete = await send(viewer, "POST", P(world, wedding, f"/tasks/{task['id']}/complete"))
    comment = await send(
        viewer,
        "POST",
        P(world, wedding, "/comments"),
        json={"target_type": "task", "target_id": task["id"], "body": "I can help with this."},
    )

    assert read.status_code == 200
    assert create.status_code == 403
    assert complete.status_code == 403
    assert comment.status_code == 201
    assert comment.json()["author_name"] == "Mira Second"


async def test_task_updates_need_the_current_version(world: World, wedding: dict[str, Any]) -> None:
    client = world["member"].client
    task = await new_task(client, world, wedding)
    url = P(world, wedding, f"/tasks/{task['id']}")

    first = await send(
        client, "PATCH", url, json={"title": "Book a jazz band"}, headers={"If-Match": '"1"'}
    )
    stale = await send(
        client, "PATCH", url, json={"title": "Book a DJ"}, headers={"If-Match": '"1"'}
    )

    assert first.status_code == 200
    assert first.headers["etag"] == '"2"'
    assert stale.status_code == 412
    assert stale.json()["code"] == "stale_version"


async def test_completing_all_tasks_completes_the_milestone(
    world: World, wedding: dict[str, Any]
) -> None:
    client = world["member"].client
    milestones = (await client.get(P(world, wedding, "/milestones"))).json()
    milestone = milestones[0]
    tasks = (
        await client.get(P(world, wedding, "/tasks"), params={"milestone_id": milestone["id"]})
    ).json()

    for task in tasks:
        done = await send(client, "POST", P(world, wedding, f"/tasks/{task['id']}/complete"))
        assert done.json()["status"] == "done"
    after = (await client.get(P(world, wedding, "/milestones"))).json()[0]
    reopened = await send(client, "POST", P(world, wedding, f"/tasks/{tasks[0]['id']}/reopen"))
    again = (await client.get(P(world, wedding, "/milestones"))).json()[0]
    feed = (await client.get(P(world, wedding, "/activity"))).json()["items"]

    assert after["completed_at"] is not None
    assert reopened.json()["completed_by_name"] is None
    assert again["completed_at"] is None
    assert {"task.completed", "milestone.completed", "task.reopened"} <= {e["verb"] for e in feed}


async def test_sharing_a_task_with_the_couple_is_audited(
    world: World, wedding: dict[str, Any]
) -> None:
    task = await new_task(world["member"].client, world, wedding)

    await send(
        world["member"].client,
        "PATCH",
        P(world, wedding, f"/tasks/{task['id']}"),
        json={"visibility": "client", "assignee_type": "client"},
        headers={"If-Match": '"1"'},
    )
    log = (
        await world["org_admin"].client.get(
            f"/api/v1/orgs/{world.org_a}/audit-log", params={"action": "task."}
        )
    ).json()["items"]

    assert [e["action"] for e in log] == ["task.shared_with_client"]
    assert log[0]["actor_name"] == "Max Member"


async def test_checklist_items(world: World, wedding: dict[str, Any]) -> None:
    client = world["member"].client
    task = await new_task(client, world, wedding, checklist=["Call venue"])
    item = task["checklist"][0]

    ticked = await send(
        client,
        "PATCH",
        P(world, wedding, f"/tasks/{task['id']}/checklist/{item['id']}"),
        json={"is_done": True},
    )
    added = await send(
        client, "POST", P(world, wedding, f"/tasks/{task['id']}/checklist"), json={"title": "Email"}
    )

    assert ticked.json()["checklist_done"] == 1
    assert added.status_code == 201
    assert [i["title"] for i in added.json()["checklist"]] == ["Call venue", "Email"]


async def test_comments_edit_own_and_admins_moderate(world: World, wedding: dict[str, Any]) -> None:
    task = await new_task(world["member"].client, world, wedding)
    created = (
        await send(
            world["member2"].client,
            "POST",
            P(world, wedding, "/comments"),
            json={"target_type": "task", "target_id": task["id"], "body": "First thought"},
        )
    ).json()
    url = P(world, wedding, f"/comments/{created['id']}")

    lead_edit = await send(world["member"].client, "PATCH", url, json={"body": "Changed"})
    own_edit = await send(world["member2"].client, "PATCH", url, json={"body": "Second thought"})
    lead_delete = await send(world["member"].client, "DELETE", url)
    listed = (
        await world["member"].client.get(
            P(world, wedding, "/comments"), params={"target_type": "task", "target_id": task["id"]}
        )
    ).json()
    admin_delete = await send(world["org_admin"].client, "DELETE", url)

    assert lead_edit.status_code == 403
    assert own_edit.json()["edited_at"] is not None
    assert lead_delete.status_code == 403
    assert [c["body"] for c in listed] == ["Second thought"]
    assert listed[0]["is_mine"] is False
    assert admin_delete.status_code == 204


async def test_my_tasks_across_weddings(world: World, wedding: dict[str, Any]) -> None:
    me = str(world["member"].membership_id)
    second = await create_wedding(world["member"].client, world, days_ahead=500)
    await new_task(
        world["member"].client,
        world,
        wedding,
        title="Mine A",
        assignee_membership_id=me,
        due_date="2027-01-01",
    )
    await new_task(
        world["member"].client,
        world,
        second,
        title="Mine B",
        assignee_membership_id=me,
        due_date="2026-12-01",
    )
    await new_task(world["member"].client, world, wedding, title="Not mine")

    mine = (await world["member"].client.get(f"/api/v1/orgs/{world.org_a}/tasks")).json()
    theirs = (await world["member2"].client.get(f"/api/v1/orgs/{world.org_a}/tasks")).json()

    assert [t["title"] for t in mine] == ["Mine B", "Mine A"]
    assert {t["project_title"] for t in mine} == {"Mia & Tom"}
    assert theirs == []


async def test_tasks_of_inaccessible_weddings_are_hidden(
    world: World, wedding: dict[str, Any]
) -> None:
    task = await new_task(world["member"].client, world, wedding)
    other_wedding = await create_wedding(world["org_admin"].client, world)
    probe = f"/api/v1/orgs/{world.org_a}/projects/{other_wedding['id']}/tasks/{task['id']}"

    assert (await world["member"].client.get(probe)).status_code == 404
    assert (await world["outsider"].client.get(P(world, wedding, "/tasks"))).status_code == 404


async def test_checklists_comments_and_activity_are_protected_by_rls(
    world: World, wedding: dict[str, Any], app_engine: AsyncEngine
) -> None:
    task = await new_task(world["member"].client, world, wedding, checklist=["A"])
    await send(
        world["member"].client,
        "POST",
        P(world, wedding, "/comments"),
        json={"target_type": "task", "target_id": task["id"], "body": "Hi"},
    )
    stranger = (await world["outsider"].client.get("/api/v1/me")).json()["id"]

    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true), "
                "set_config('app.role', 'member', true)"
            ),
            {"o": str(world.org_a), "u": stranger},
        )
        counts = [
            (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
            for t in ("task_checklist_items", "comments", "activity_events")
        ]

    assert counts == [0, 0, 0]


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_reorder_and_delete_tasks(world: World, wedding: dict[str, Any]) -> None:
    client = world["member"].client
    first = await new_task(client, world, wedding, title="First", due_date="2027-02-01")
    second = await new_task(client, world, wedding, title="Second", due_date="2027-02-01")

    reordered = await send(
        client,
        "POST",
        P(world, wedding, "/tasks/reorder"),
        json={"items": [{"id": second["id"], "position": 0}, {"id": first["id"], "position": 1}]},
    )
    same_day = [
        t["title"]
        for t in (await client.get(P(world, wedding, "/tasks"))).json()
        if t["due_date"] == "2027-02-01"
    ]
    deleted = await send(client, "DELETE", P(world, wedding, f"/tasks/{first['id']}"))
    gone = await client.get(P(world, wedding, f"/tasks/{first['id']}"))

    assert reordered.status_code == 204
    assert same_day == ["Second", "First"]
    assert deleted.status_code == 204
    assert gone.status_code == 404
    titles = [t["title"] for t in (await client.get(P(world, wedding, "/tasks"))).json()]
    assert "First" not in titles and "Second" in titles


async def test_checklist_items_are_renamed_and_removed(
    world: World, wedding: dict[str, Any]
) -> None:
    client = world["member"].client
    task = await new_task(client, world, wedding, checklist=["Call venue", "Email band"])
    first, second = task["checklist"]
    base = P(world, wedding, f"/tasks/{task['id']}/checklist")

    renamed = await send(client, "PATCH", f"{base}/{first['id']}", json={"title": "Call venue!"})
    removed = await send(client, "DELETE", f"{base}/{second['id']}")

    assert [i["title"] for i in renamed.json()["checklist"]] == ["Call venue!", "Email band"]
    assert [i["title"] for i in removed.json()["checklist"]] == ["Call venue!"]
    after = (await client.get(P(world, wedding, f"/tasks/{task['id']}"))).json()
    assert [i["title"] for i in after["checklist"]] == ["Call venue!"]
    assert after["checklist_total"] == 1
