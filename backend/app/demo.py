"""A demo organization with invented data, for trying the platform and for the pilot kickoff.

Everything goes through the real API in-process, so permissions, audit entries and
notifications behave exactly as in use. All people, places and addresses are fictional; email
addresses use the reserved example.com domain, so no real mailbox is ever contacted.
"""

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient

from app.core.ids import uuid7
from app.core.security import hash_token, new_token
from app.db.session import get_sessionmaker
from app.db.tenant import set_tenant_context
from app.organizations.models import Invitation, Organization, OrgRole
from app.organizations.service import _create_invitation, create_organization

PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

WEDDINGS: list[dict[str, Any]] = [
    {
        "couple": "Lena & Jonas",
        "days": 46,
        "venue": "Gut Lindenhof",
        "guests": 120,
        "budget": 38_000_00,
        "items": [
            ("Venue", "Gut Lindenhof, Scheune", 12_500_00, 12_500_00, True),
            ("Catering", "Küche Feinsinn", 9_800_00, 9_200_00, True),
            ("Photography", "Lichtblick Fotografie", 3_200_00, 3_200_00, True),
            ("Flowers & Decor", "Blütenwerk", 2_900_00, None, False),
        ],
        "events": [
            ("Final tasting", 10, "15:00", "16:30", "Küche Feinsinn", True),
            ("Walkthrough with the venue", 21, "11:00", "12:00", "Gut Lindenhof", True),
            ("Vendor briefing", 30, "09:30", "10:30", None, False),
        ],
        "done": 13,
    },
    {
        "couple": "Sophie & Amir",
        "days": 162,
        "venue": "Schloss Elbblick",
        "guests": 80,
        "budget": 29_000_00,
        "items": [
            ("Venue", "Schloss Elbblick", 9_000_00, 9_000_00, True),
            ("Music", "Trio Abendrot", 2_400_00, 2_600_00, True),
        ],
        "events": [("Dress fitting", 40, "10:00", "11:00", "Atelier Weiß", True)],
        "done": 6,
    },
    {
        "couple": "Clara & Max",
        "days": 301,
        "venue": None,
        "guests": None,
        "budget": 0,
        "items": [],
        "events": [("First meeting", 3, "17:00", "18:00", "Studio", False)],
        "done": 1,
    },
]


def _password() -> str:
    return "-".join(secrets.token_urlsafe(4) for _ in range(4))


async def _accept(app: Any, token: str, name: str, password: str) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://demo.local")
    r = await client.post(
        f"/api/v1/auth/invitations/{token}/accept",
        json={"full_name": name, "password": password},
    )
    r.raise_for_status()
    return client


async def _call(client: AsyncClient, method: str, path: str, **kw: Any) -> Any:
    headers = {"X-CSRF-Token": client.cookies.get("__Host-csrf") or "", **kw.pop("headers", {})}
    r = await client.request(method, f"/api/v1{path}", headers=headers, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text}")
    return r.json() if r.content else None


async def seed_demo(
    name: str = "Atelier Lumière (Demo)", domain: str = "example.com"
) -> dict[str, str]:
    import logging

    from app.main import create_app

    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = create_app()
    suffix = uuid.uuid4().hex[:6]
    emails = {
        "admin": f"demo-admin-{suffix}@{domain}",
        "planner": f"demo-planner-{suffix}@{domain}",
        "couple": f"demo-couple-{suffix}@{domain}",
    }
    passwords = {k: _password() for k in emails}

    async with get_sessionmaker()() as db:
        org, link = await create_organization(db, name=name, admin_email=emails["admin"])
        await db.commit()
    org_id = org.id
    admin = await _accept(app, link.rsplit("/", 1)[1], "Lena Hoffmann", passwords["admin"])

    async with get_sessionmaker()() as db:
        await set_tenant_context(
            db, organization_id=org_id, user_id=uuid.UUID(int=0), role="org_admin"
        )
        org_row = await db.get(Organization, org_id)
        assert org_row is not None
        _, planner_link = await _create_invitation(
            db, org_row, emails["planner"], OrgRole.MEMBER, None
        )
        await db.commit()
    planner = await _accept(
        app, planner_link.rsplit("/", 1)[1], "Jana Becker", passwords["planner"]
    )
    members = await _call(admin, "GET", f"/orgs/{org_id}/members")
    planner_membership = next(m["id"] for m in members if m["email"] == emails["planner"])

    base = f"/orgs/{org_id}"
    first_wedding: dict[str, Any] | None = None
    for spec in WEDDINGS:
        body: dict[str, Any] = {
            "new_client_name": spec["couple"],
            "wedding_date": (date.today() + timedelta(days=spec["days"])).isoformat(),
            "guest_count_planned": spec["guests"],
        }
        if spec["venue"]:
            body["venue_name"] = spec["venue"]
        wedding = await _call(admin, "POST", f"{base}/projects", json=body)
        first_wedding = first_wedding or wedding
        path = f"{base}/projects/{wedding['id']}"
        await _call(
            admin,
            "POST",
            f"{path}/members",
            json={"membership_id": planner_membership, "project_role": "planner"},
        )
        tasks = await _call(admin, "GET", f"{path}/tasks")
        for task in tasks[: spec["done"]]:
            await _call(admin, "POST", f"{path}/tasks/{task['id']}/complete")
        if spec["budget"]:
            budget = await _call(admin, "GET", f"{path}/budget")
            await _call(
                admin,
                "PATCH",
                f"{path}/budget",
                json={"total_cents": spec["budget"]},
                headers={"If-Match": f'"{budget["version"]}"'},
            )
            categories = {c["name"]: c["id"] for c in budget["categories"]}
            for category, title, planned, contracted, shared in spec["items"]:
                view = await _call(
                    admin,
                    "POST",
                    f"{path}/budget/items",
                    json={
                        "category_id": categories[category],
                        "title": title,
                        "planned_cents": planned,
                        "contracted_cents": contracted,
                        "visibility": "client" if shared else "internal",
                    },
                )
                if contracted:
                    item = next(
                        i for c in view["categories"] for i in c["items"] if i["title"] == title
                    )
                    await _call(
                        admin,
                        "POST",
                        f"{path}/budget/items/{item['id']}/payments",
                        json={"label": "Deposit", "amount_cents": contracted // 3, "paid": True},
                    )
                    await _call(
                        admin,
                        "POST",
                        f"{path}/budget/items/{item['id']}/payments",
                        json={
                            "label": "Final payment",
                            "amount_cents": contracted - contracted // 3,
                            "due_date": (
                                date.today() + timedelta(days=max(spec["days"] - 14, 7))
                            ).isoformat(),
                        },
                    )
        for title, days, start, end, location, shared in spec["events"]:
            day = date.today() + timedelta(days=days)
            starts = datetime.fromisoformat(f"{day}T{start}:00").astimezone(UTC)
            ends = datetime.fromisoformat(f"{day}T{end}:00").astimezone(UTC)
            await _call(
                planner,
                "POST",
                f"{path}/events",
                json={
                    "title": title,
                    "starts_at": starts.isoformat(),
                    "ends_at": ends.isoformat(),
                    "location": location,
                    "visibility": "client" if shared else "internal",
                },
            )

    assert first_wedding is not None
    path = f"{base}/projects/{first_wedding['id']}"
    for title, filename, category, shared in [
        ("Timeline for the day", "Timeline.pdf", "planning", True),
        ("Venue contract", "Venue contract.pdf", "contract", False),
    ]:
        await _call(
            admin,
            "POST",
            f"{path}/documents",
            files={"file": (filename, PDF, "application/pdf")},
            data={
                "title": title,
                "category": category,
                "visibility": "client" if shared else "internal",
            },
        )

    # The couple's portal login for the first wedding.
    token = new_token()
    async with get_sessionmaker()() as db:
        await set_tenant_context(
            db, organization_id=org_id, user_id=uuid.UUID(int=0), role="org_admin"
        )
        db.add(
            Invitation(
                id=uuid7(),
                organization_id=org_id,
                email=emails["couple"],
                role=OrgRole.CLIENT,
                project_id=uuid.UUID(first_wedding["id"]),
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        await db.commit()
    couple = await _accept(app, token, "Lena Schneider", passwords["couple"])
    portal = await _call(couple, "GET", "/portal/projects")
    await _call(
        couple,
        "POST",
        f"/portal/projects/{portal[0]['id']}/tasks/"
        f"{(await _call(couple, 'GET', f'/portal/projects/{portal[0]["id"]}/tasks'))[-1]['id']}"
        "/comments",
        json={"body": "Could we add a vegan option to the menu?"},
    )
    for client in (admin, planner, couple):
        await client.aclose()

    return {
        "organization": name,
        **{f"{role}_email": email for role, email in emails.items()},
        **{f"{role}_password": pw for role, pw in passwords.items()},
    }
