"""GDPR tools: client export and erasure, personal export, account deletion, consents,
retention and the end of couple access after archiving."""

import io
import json
import zipfile
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents import storage
from tests.conftest import new_client
from tests.helpers import PASSWORD, World, send
from tests.test_budget_portal import COUPLE
from tests.test_budget_portal import couple as couple
from tests.test_documents import PDF, upload
from tests.test_tasks import P, new_task
from tests.test_tasks import wedding as wedding
from tests.test_tasks import world as world


def org(world: World, path: str) -> str:
    return f"/api/v1/orgs/{world.org_a}{path}"


async def test_client_export_contains_data_and_files(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    await new_task(lead, world, wedding, title="Choose rings", description="Gold, size 54")
    await upload(lead, world, wedding, title="Venue contract")
    client_id = wedding["client_id"]

    member = await lead.get(org(world, f"/clients/{client_id}/export"))
    response = await world["org_admin"].client.get(org(world, f"/clients/{client_id}/export"))

    assert member.status_code == 403  # org admins only
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    data = json.loads(archive.read("data.json"))
    assert data["client"]["display_name"] == "Mia & Tom"
    wedding_data = data["weddings"][0]
    assert any(t["description"] == "Gold, size 54" for t in wedding_data["tasks"])
    assert wedding_data["documents"][0]["title"] == "Venue contract"
    assert "storage_key" not in wedding_data["document_versions"][0]
    assert data["portal_accounts"] == [
        {"email": COUPLE, "full_name": "Mia Becker", "status": "active"}
    ]
    files = [n for n in archive.namelist() if n.startswith("files/")]
    assert len(files) == 1 and files[0].endswith("Venue contract.pdf")
    assert archive.read(files[0]) == PDF


async def test_erase_client_removes_everything(
    world: World,
    wedding: dict[str, Any],
    couple: AsyncClient,
    owner_engine: AsyncEngine,
) -> None:
    lead = world["member"].client
    admin = world["org_admin"].client
    await upload(lead, world, wedding, visibility="client")
    client_id = wedding["client_id"]
    path = org(world, f"/clients/{client_id}/erase")

    mismatch = await send(admin, "POST", path, json={"confirm": "Mia"})
    assert mismatch.status_code == 422
    assert mismatch.json()["code"] == "confirmation_mismatch"
    response = await send(admin, "POST", path, json={"confirm": "Mia & Tom"})

    assert response.status_code == 200, response.text
    assert response.json() == {"weddings": 1, "files": 1, "portal_accounts": 1}
    assert storage.MEMORY == {}
    assert (await lead.get(P(world, wedding))).status_code == 404
    assert (await couple.get("/api/v1/portal/projects")).json() == []
    async with owner_engine.begin() as conn:
        counts = {
            table: (
                await conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE organization_id = :o"),
                    {"o": world.org_a},
                )
            ).scalar_one()
            for table in ("clients", "client_contacts", "projects", "tasks", "documents", "budgets")
        }
        actions = (
            (
                await conn.execute(
                    text("SELECT action FROM audit_log WHERE resource_id = :c"), {"c": client_id}
                )
            )
            .scalars()
            .all()
        )
    assert counts == dict.fromkeys(counts, 0)
    assert "privacy.client_erased" in actions


async def test_erase_needs_a_recent_password_confirmation(
    world: World, wedding: dict[str, Any]
) -> None:
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        await db.execute(text("UPDATE sessions SET reauth_at = now() - interval '1 hour'"))
        await db.commit()

    response = await send(
        world["org_admin"].client,
        "POST",
        org(world, f"/clients/{wedding['client_id']}/erase"),
        json={"confirm": "Mia & Tom"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "reauth_required"


async def test_personal_export(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    task = await new_task(lead, world, wedding)
    await send(
        lead,
        "POST",
        P(world, wedding, "/comments"),
        json={"target_type": "task", "target_id": task["id"], "body": "My own words"},
    )

    response = await lead.get("/api/v1/me/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["account"]["email"] == "member@example.com"
    assert data["organizations"][0]["organization"] == "Atelier Test"
    assert data["organizations"][0]["comments_written"][0]["body"] == "My own words"
    assert data["sessions"][0]["user_agent"] is not None or data["sessions"]
    assert any(a["action"] == "invitation.accepted" for a in data["activity"])


async def test_delete_account(app: FastAPI, world: World, wedding: dict[str, Any]) -> None:
    member = world["member2"].client

    wrong = await send(
        member, "POST", "/api/v1/me/delete", json={"password": "nope", "confirm": "DELETE"}
    )
    ok = await send(
        member, "POST", "/api/v1/me/delete", json={"password": PASSWORD, "confirm": "DELETE"}
    )

    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_current_password"
    assert ok.status_code == 204
    assert (await member.get("/api/v1/me")).status_code == 401
    relogin = await new_client(app).post(
        "/api/v1/auth/login", json={"email": "member2@example.com", "password": PASSWORD}
    )
    assert relogin.status_code == 401
    team = (await world["org_admin"].client.get(org(world, "/members"))).json()
    assert "member2@example.com" not in [m["email"] for m in team]


async def test_last_admin_cannot_delete_their_account(world: World) -> None:
    response = await send(
        world["org_admin"].client,
        "POST",
        "/api/v1/me/delete",
        json={"password": PASSWORD, "confirm": "DELETE"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "last_admin"


async def test_consents(
    world: World, wedding: dict[str, Any], couple: AsyncClient, owner_engine: AsyncEngine
) -> None:
    path = f"/api/v1/portal/projects/{wedding['id']}/consents"

    initial = (await couple.get(path)).json()
    assert {c["kind"]: c["granted"] for c in initial} == {"portfolio": None, "reviews": None}
    await send(couple, "PUT", path, json={"kind": "portfolio", "granted": True})
    after = await send(couple, "PUT", path, json={"kind": "portfolio", "granted": False})

    assert {c["kind"]: c["granted"] for c in after.json()}["portfolio"] is False
    planner_view = (await world["member"].client.get(P(world, wedding, "/consents"))).json()
    assert planner_view[0]["full_name"] == "Mia Becker"
    assert {c["kind"]: c["granted"] for c in planner_view[0]["consents"]}["portfolio"] is False
    async with owner_engine.begin() as conn:
        actions = (
            (
                await conn.execute(
                    text(
                        "SELECT action FROM audit_log WHERE action LIKE 'consent.%' "
                        "ORDER BY created_at"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert actions == ["consent.granted", "consent.withdrawn"]


async def test_couples_read_only_their_own_audit_entries(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    export = (await couple.get("/api/v1/me/export")).json()

    assert {a["action"] for a in export["activity"]} >= {"invitation.accepted"}
    # The organization's audit log stays closed to them.
    blocked = await couple.get(org(world, "/audit-log"))
    assert blocked.status_code == 403


async def test_couple_access_ends_after_the_archive_period(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    from app.jobs.retention import purge

    await send(world["member"].client, "POST", P(world, wedding, "/archive"))
    assert len((await couple.get("/api/v1/portal/projects")).json()) == 1  # within 90 days

    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        await db.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(world.org_a)})
        await db.execute(text("SELECT set_config('app.role', 'org_admin', true)"))
        await db.execute(text("UPDATE projects SET archived_at = now() - interval '91 days'"))
        await db.commit()

    assert (await couple.get("/api/v1/portal/projects")).json() == []
    assert (await couple.get(f"/api/v1/portal/projects/{wedding['id']}")).status_code == 404
    removed = await purge({})
    assert removed["couple_access_after_archive"] == 1


async def test_retention_removes_expired_sessions(world: World, owner_engine: AsyncEngine) -> None:
    from app.jobs.retention import purge

    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE sessions SET expires_at = now() - interval '40 days' WHERE ctid IN "
                "(SELECT ctid FROM sessions LIMIT 1)"
            )
        )

    removed = await purge({})

    assert removed["sessions"] == 1


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_retention_removes_stale_links_and_old_notification_log(
    app: FastAPI, world: World, owner_engine: AsyncEngine
) -> None:
    from app.jobs.retention import purge

    admin = world["org_admin"].client
    invited = await send(
        admin,
        "POST",
        org(world, "/invitations"),
        json={"email": "late@example.com", "role": "member"},
    )
    assert invited.status_code == 201, invited.text
    await new_client(app).post("/api/v1/auth/password/forgot", json={"email": "member@example.com"})
    async with owner_engine.begin() as conn:
        user_id = (
            await conn.execute(text("SELECT id FROM users WHERE email = 'member@example.com'"))
        ).scalar_one()
        await conn.execute(
            text(
                "UPDATE invitations SET expires_at = now() - interval '91 days' "
                "WHERE email = 'late@example.com'"
            )
        )
        await conn.execute(
            text("UPDATE password_reset_tokens SET expires_at = now() - interval '8 days'")
        )
        await conn.execute(
            text(
                "INSERT INTO notification_log (id, organization_id, user_id, kind, ref, created_at)"
                " VALUES (gen_random_uuid(), :o, :u, 'digest', 'old', now() - interval '91 days'), "
                "(gen_random_uuid(), :o, :u, 'digest', 'recent', now() - interval '10 days')"
            ),
            {"o": world.org_a, "u": user_id},
        )

    removed = await purge({})

    assert removed["invitations"] == 1
    assert removed["password_reset_tokens"] == 1
    assert removed["notification_log"] == 1
    async with owner_engine.begin() as conn:
        left = (
            (await conn.execute(text("SELECT ref FROM notification_log ORDER BY ref")))
            .scalars()
            .all()
        )
        pending = (
            await conn.execute(
                text("SELECT count(*) FROM invitations WHERE email = 'late@example.com'")
            )
        ).scalar_one()
    assert left == ["recent"]
    assert pending == 0
