"""Appointments, the combined calendar and private iCal feeds."""

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient

from app.events import ics
from tests.helpers import World, send
from tests.test_budget_portal import add_item, item_named
from tests.test_budget_portal import couple as couple
from tests.test_tasks import P, new_task
from tests.test_tasks import wedding as wedding
from tests.test_tasks import world as world

TODAY = date.today()


def soon(days: int) -> str:
    return (TODAY + timedelta(days=days)).isoformat()


async def new_event(client: AsyncClient, world: World, wedding: dict[str, Any], **body: Any) -> Any:
    payload = {
        "title": "Cake tasting",
        "starts_at": f"{soon(3)}T15:00:00+01:00",
        "ends_at": f"{soon(3)}T16:30:00+01:00",
        "location": "Konditorei Süß, Hamburg",
        **body,
    }
    response = await send(client, "POST", P(world, wedding, "/events"), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def calendar_url(world: World) -> str:
    return f"/api/v1/orgs/{world.org_a}/calendar"


async def test_create_timed_and_all_day_events(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    timed = await new_event(lead, world, wedding)
    all_day = await new_event(
        lead,
        world,
        wedding,
        title="Dress fittings",
        all_day=True,
        starts_at=None,
        ends_at=None,
        start_date=soon(10),
        end_date=soon(11),
    )

    assert timed["start_date"] == soon(3)
    assert timed["all_day"] is False
    assert all_day["start_date"] == soon(10)
    assert all_day["end_date"] == soon(11)
    events = (await lead.get(P(world, wedding, "/events"))).json()
    assert [e["title"] for e in events] == ["Cake tasting", "Dress fittings"]


async def test_event_validation(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    bad = [
        {"title": "x", "starts_at": f"{soon(3)}T15:00:00"},  # no time zone
        {"title": "x", "starts_at": f"{soon(3)}T15:00:00Z", "ends_at": f"{soon(2)}T15:00:00Z"},
        {"title": "x", "all_day": True},
        {"title": "x", "all_day": True, "start_date": soon(5), "end_date": soon(1)},
    ]
    for body in bad:
        response = await send(lead, "POST", P(world, wedding, "/events"), json=body)
        assert response.status_code == 422, body


async def test_update_needs_current_version_and_viewers_cannot_write(
    world: World, wedding: dict[str, Any]
) -> None:
    event = await new_event(world["member"].client, world, wedding)
    body = {"title": "Cake tasting (moved)", "starts_at": f"{soon(4)}T10:00:00+01:00"}
    path = P(world, wedding, f"/events/{event['id']}")

    stale = await send(world["member"].client, "PUT", path, json=body, headers={"If-Match": '"0"'})
    ok = await send(
        world["member"].client,
        "PUT",
        path,
        json=body,
        headers={"If-Match": f'"{event["version"]}"'},
    )
    viewer = await send(world["member2"].client, "POST", P(world, wedding, "/events"), json=body)

    assert stale.status_code == 412
    assert ok.status_code == 200
    assert ok.json()["title"] == "Cake tasting (moved)"
    assert ok.json()["ends_at"] is None
    assert viewer.status_code == 403
    assert (await send(world["member"].client, "DELETE", path)).status_code == 204


async def test_combined_calendar(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    await new_event(lead, world, wedding)
    mine = await new_task(
        lead,
        world,
        wedding,
        title="Send invitations",
        due_date=soon(5),
        assignee_membership_id=str(world["member"].membership_id),
    )
    view = await add_item(lead, world, wedding, "Venue", planned_cents=1000_00)
    item = item_named(view, "Venue")
    await send(
        lead,
        "POST",
        P(world, wedding, f"/budget/items/{item['id']}/payments"),
        json={"label": "Venue deposit", "amount_cents": 500_00, "due_date": soon(6)},
    )
    params = {"start": soon(0), "end": soon(10)}

    items = (await lead.get(calendar_url(world), params=params)).json()
    kinds = {(i["kind"], i["title"]) for i in items}
    assert ("event", "Cake tasting") in kinds
    assert ("task", "Send invitations") in kinds
    assert ("payment", "Venue deposit") in kinds
    assert next(i for i in items if i["id"] == mine["id"])["assigned_to_me"] is True
    assert [i["date"] for i in items] == sorted(i["date"] for i in items)

    only_mine = (await lead.get(calendar_url(world), params={**params, "mine": True})).json()
    assert {i["title"] for i in only_mine if i["kind"] == "task"} == {"Send invitations"}

    wedding_day = (
        await lead.get(calendar_url(world), params={"start": soon(290), "end": soon(310)})
    ).json()
    assert [(i["kind"], i["date"]) for i in wedding_day if i["kind"] == "wedding"] == [
        ("wedding", soon(300))
    ]


async def test_calendar_respects_wedding_access_and_ranges(
    world: World, wedding: dict[str, Any]
) -> None:
    await new_event(world["member"].client, world, wedding)
    params = {"start": soon(0), "end": soon(10)}

    # org_admin sees every wedding; an outsider's org does not include this one.
    assert any((await world["org_admin"].client.get(calendar_url(world), params=params)).json())
    outsider = await world["outsider"].client.get(
        f"/api/v1/orgs/{world.org_b}/calendar", params=params
    )
    assert outsider.json() == []
    assert (
        await world["outsider"].client.get(calendar_url(world), params=params)
    ).status_code == 404
    assert (await world["client"].client.get(calendar_url(world), params=params)).status_code == 403
    too_long = await world["member"].client.get(
        calendar_url(world), params={"start": soon(0), "end": soon(200)}
    )
    assert too_long.status_code == 422


async def test_couples_see_only_shared_appointments(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    await new_event(lead, world, wedding, title="Venue walkthrough", visibility="client")
    await new_event(lead, world, wedding, title="Vendor briefing")
    await new_task(
        lead,
        world,
        wedding,
        title="Choose rings",
        due_date=soon(4),
        assignee_type="client",
        visibility="client",
    )
    await new_task(lead, world, wedding, title="Internal check", due_date=soon(4))

    items = (
        await couple.get(
            f"/api/v1/portal/projects/{wedding['id']}/calendar",
            params={"start": soon(0), "end": soon(400)},
        )
    ).json()

    titles = {i["title"] for i in items}
    assert {"Venue walkthrough", "Choose rings", "Mia & Tom"} <= titles
    assert "Vendor briefing" not in titles
    assert "Internal check" not in titles
    assert "visibility" not in items[0]


# --- Feeds ---------------------------------------------------------------------------------


async def test_feed_lifecycle(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    await new_event(lead, world, wedding, location="Hamburg; Altona, Elbe")
    await new_task(
        lead,
        world,
        wedding,
        title="Book the band",
        due_date=soon(5),
        assignee_membership_id=str(world["member"].membership_id),
    )
    await new_task(lead, world, wedding, title="Someone else's task", due_date=soon(5))
    feed_path = f"/api/v1/orgs/{world.org_a}/calendar/feed"

    assert (await lead.get(feed_path)).json() == {
        "active": False,
        "created_at": None,
        "last_used_at": None,
    }
    created = (await send(lead, "POST", feed_path)).json()
    url = created["url"].removeprefix("https://app.test")
    assert url.startswith("/api/v1/calendar-feeds/") and url.endswith(".ics")

    anonymous = world["anonymous"].client
    response = await anonymous.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    body = response.text
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert "SUMMARY:Cake tasting · Mia & Tom" in body
    assert "LOCATION:Hamburg\; Altona\\, Elbe" in body
    assert "SUMMARY:Due: Book the band · Mia & Tom" in body
    assert "Someone else" not in body
    assert "SUMMARY:Wedding: Mia & Tom" in body
    assert "DESCRIPTION" not in body
    assert (await lead.get(feed_path)).json()["last_used_at"] is not None

    rotated = (await send(lead, "POST", feed_path)).json()
    assert (await anonymous.get(url)).status_code == 404
    assert (await anonymous.get(rotated["url"].removeprefix("https://app.test"))).status_code == 200

    await send(lead, "DELETE", feed_path)
    assert (await anonymous.get(rotated["url"].removeprefix("https://app.test"))).status_code == 404
    assert (await anonymous.get("/api/v1/calendar-feeds/" + "x" * 43 + ".ics")).status_code == 404


async def test_feeds_are_private_to_their_owner(world: World, wedding: dict[str, Any]) -> None:
    await send(world["member"].client, "POST", f"/api/v1/orgs/{world.org_a}/calendar/feed")

    other = await world["member2"].client.get(f"/api/v1/orgs/{world.org_a}/calendar/feed")
    admin = await world["org_admin"].client.get(f"/api/v1/orgs/{world.org_a}/calendar/feed")

    assert other.json()["active"] is False
    assert admin.json()["active"] is False


async def test_feed_stops_when_the_membership_ends(world: World, wedding: dict[str, Any]) -> None:
    created = (
        await send(world["member2"].client, "POST", f"/api/v1/orgs/{world.org_a}/calendar/feed")
    ).json()
    url = created["url"].removeprefix("https://app.test")
    assert (await world["anonymous"].client.get(url)).status_code == 200

    from sqlalchemy import text

    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        await db.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(world.org_a)})
        await db.execute(
            text("UPDATE memberships SET status = 'disabled' WHERE id = :m"),
            {"m": str(world["member2"].membership_id)},
        )
        await db.commit()

    assert (await world["anonymous"].client.get(url)).status_code == 404


async def test_couple_feed_contains_only_shared_items(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    await new_event(lead, world, wedding, title="Venue walkthrough", visibility="client")
    await new_event(lead, world, wedding, title="Vendor briefing")
    created = (
        await send(couple, "POST", f"/api/v1/portal/projects/{wedding['id']}/calendar/feed")
    ).json()

    body = (
        await world["anonymous"].client.get(created["url"].removeprefix("https://app.test"))
    ).text

    assert "SUMMARY:Venue walkthrough\r\n" in body
    assert "Vendor briefing" not in body


def test_ics_folding_and_escaping() -> None:
    entry = ics.IcsEntry(
        uid="event-1@test",
        summary="Ü" * 60 + ", done; \\ ok\nnext",
        start=date(2027, 6, 12),
        end=date(2027, 6, 13),
    )
    text = ics.build("Test", [entry])
    lines = text.split("\r\n")

    assert all(len(line.encode()) <= 75 for line in lines)
    unfolded = text.replace("\r\n ", "")
    assert "SUMMARY:" + "Ü" * 60 + "\\, done\; \\\\ ok\\nnext" in unfolded
    assert "DTSTART;VALUE=DATE:20270612" in unfolded
