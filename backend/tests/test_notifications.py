"""Email notifications: preferences, task assignment, comments and the daily digest."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from app.notifications.digest import digest_for_organization, send_daily_digests
from app.notifications.mailer import OUTBOX
from tests.helpers import World, send
from tests.test_budget_portal import COUPLE
from tests.test_budget_portal import couple as couple
from tests.test_calendar import new_event, soon
from tests.test_tasks import P, new_task
from tests.test_tasks import wedding as wedding
from tests.test_tasks import world as world

MEMBER2 = "member2@example.com"


def prefs(world: World) -> str:
    return f"/api/v1/orgs/{world.org_a}/notification-preferences"


def to(address: str) -> list[Any]:
    return [e for e in OUTBOX if e.to == address]


async def test_preferences_default_on_and_are_per_user(world: World) -> None:
    member = world["member"].client
    assert (await member.get(prefs(world))).json() == {
        "task_assigned": True,
        "comments": True,
        "documents": True,
        "daily_digest": True,
    }

    updated = await send(member, "PATCH", prefs(world), json={"daily_digest": False})

    assert updated.json()["daily_digest"] is False
    assert (await member.get(prefs(world))).json()["daily_digest"] is False
    assert (await world["member2"].client.get(prefs(world))).json()["daily_digest"] is True


async def test_assignee_is_emailed_but_not_the_actor(world: World, wedding: dict[str, Any]) -> None:
    OUTBOX.clear()
    lead = world["member"].client
    await new_task(
        lead,
        world,
        wedding,
        title="Own task",
        assignee_membership_id=str(world["member"].membership_id),
    )
    assert to("member@example.com") == []

    task = await new_task(
        lead,
        world,
        wedding,
        title="Confirm florist",
        assignee_membership_id=str(world["member2"].membership_id),
    )

    emails = to(MEMBER2)
    assert len(emails) == 1
    assert emails[0].subject == "New task for you: Confirm florist"
    assert f"/app/weddings/{wedding['id']}/tasks?task={task['id']}" in emails[0].text
    assert "/app/notifications" in emails[0].text


async def test_reassigning_notifies_the_new_assignee_once(
    world: World, wedding: dict[str, Any]
) -> None:
    lead = world["member"].client
    task = await new_task(lead, world, wedding, title="Venue visit")
    OUTBOX.clear()
    path = P(world, wedding, f"/tasks/{task['id']}")

    first = await send(
        lead,
        "PATCH",
        path,
        json={"assignee_membership_id": str(world["member2"].membership_id)},
        headers={"If-Match": f'"{task["version"]}"'},
    )
    await send(
        lead,
        "PATCH",
        path,
        json={"title": "Venue visit (Friday)"},
        headers={"If-Match": f'"{first.json()["version"]}"'},
    )

    assert len(to(MEMBER2)) == 1


async def test_opt_out_is_respected(world: World, wedding: dict[str, Any]) -> None:
    await send(world["member2"].client, "PATCH", prefs(world), json={"task_assigned": False})
    OUTBOX.clear()

    await new_task(
        world["member"].client,
        world,
        wedding,
        assignee_membership_id=str(world["member2"].membership_id),
    )

    assert to(MEMBER2) == []


async def test_comments_reach_the_assignee_without_the_text(
    world: World, wedding: dict[str, Any]
) -> None:
    lead = world["member"].client
    task = await new_task(
        lead,
        world,
        wedding,
        title="Menu",
        assignee_membership_id=str(world["member2"].membership_id),
    )
    OUTBOX.clear()

    await send(
        lead,
        "POST",
        P(world, wedding, "/comments"),
        json={"target_type": "task", "target_id": task["id"], "body": "Secret allergy details"},
    )

    emails = to(MEMBER2)
    assert len(emails) == 1
    assert emails[0].subject == "New comment on “Menu”"
    assert "Secret allergy" not in emails[0].text


async def test_couple_comments_reach_the_lead_and_replies_reach_the_couple(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    task = await new_task(
        lead, world, wedding, title="Choose rings", assignee_type="client", visibility="client"
    )
    OUTBOX.clear()

    await send(
        couple,
        "POST",
        f"/api/v1/portal/projects/{wedding['id']}/tasks/{task['id']}/comments",
        json={"body": "Can we do this next week?"},
    )
    assert [e.subject for e in to("member@example.com")] == ["New comment on “Choose rings”"]

    await send(
        lead,
        "POST",
        P(world, wedding, "/comments"),
        json={
            "target_type": "task",
            "target_id": task["id"],
            "body": "Sure!",
            "visibility": "client",
        },
    )
    couple_emails = to(COUPLE)
    assert len(couple_emails) == 1
    assert "/portal/tasks" in couple_emails[0].text
    assert "/portal/notifications" in couple_emails[0].text


async def test_daily_digest(world: World, wedding: dict[str, Any], couple: AsyncClient) -> None:
    lead = world["member"].client
    today = date.today()
    await new_event(
        lead,
        world,
        wedding,
        title="Cake tasting",
        starts_at=f"{today.isoformat()}T15:00:00+00:00",
        ends_at=None,
        visibility="client",
    )
    await new_task(
        lead,
        world,
        wedding,
        title="Call the band",
        due_date=soon(1),
        assignee_membership_id=str(world["member"].membership_id),
    )
    await new_task(
        lead,
        world,
        wedding,
        title="Old one",
        due_date=(today - timedelta(days=3)).isoformat(),
        assignee_membership_id=str(world["member"].membership_id),
    )
    await new_task(
        lead,
        world,
        wedding,
        title="Choose rings",
        due_date=soon(1),
        assignee_type="client",
        visibility="client",
    )
    await send(world["member2"].client, "PATCH", prefs(world), json={"daily_digest": False})
    OUTBOX.clear()

    sent = await digest_for_organization(world.org_a, today)

    member_mail = to("member@example.com")
    assert len(member_mail) == 1
    text = member_mail[0].text
    assert "Today 16:00: Cake tasting · Mia & Tom" in text  # Europe/Berlin
    assert "Tomorrow: Due: Call the band · Mia & Tom" in text
    assert "1 overdue task waiting for you" in text
    assert "Choose rings" not in text
    couple_mail = to(COUPLE)
    assert len(couple_mail) == 1
    assert "Choose rings" in couple_mail[0].text
    assert "Call the band" not in couple_mail[0].text
    assert to(MEMBER2) == []
    assert sent == len(OUTBOX)

    # Once per day.
    assert await digest_for_organization(world.org_a, today) == 0


async def test_digest_runs_at_the_local_hour(world: World, wedding: dict[str, Any]) -> None:
    await new_task(
        world["member"].client,
        world,
        wedding,
        title="Call the band",
        due_date=date.today().isoformat(),
        assignee_membership_id=str(world["member"].membership_id),
    )
    OUTBOX.clear()
    today = date.today()

    # 07:xx in Berlin is 05:xx or 06:xx UTC depending on daylight saving time.
    berlin_seven = datetime(today.year, today.month, today.day, 6, 5, tzinfo=UTC)
    from zoneinfo import ZoneInfo

    local_hour = berlin_seven.astimezone(ZoneInfo("Europe/Berlin")).hour
    berlin_seven -= timedelta(hours=local_hour - 7)

    assert await send_daily_digests({}, now=berlin_seven - timedelta(hours=1)) == 0
    assert await send_daily_digests({}, now=berlin_seven) >= 1
