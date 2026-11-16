"""Moodboards: boards, images, hearts, comments, visibility for the couple, privacy."""

import io
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.documents import storage
from app.notifications.mailer import OUTBOX
from tests.helpers import World, send
from tests.test_budget_portal import couple as couple
from tests.test_tasks import P
from tests.test_tasks import wedding as wedding
from tests.test_tasks import world as world


def photo(color: tuple[int, int, int] = (200, 120, 90), gps: bool = True) -> bytes:
    """A generated JPEG; with GPS coordinates in its EXIF like a phone photo."""
    image = Image.new("RGB", (1200, 900), color)
    exif = image.getexif()
    if gps:
        exif[0x8825] = {1: "N", 2: (52.0, 31.0, 12.0), 3: "E", 4: (13.0, 24.0, 18.0)}
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def MB(world: World, wedding: dict[str, Any], path: str = "") -> str:
    return P(world, wedding, f"/moodboards{path}")


def portal(wedding: dict[str, Any], path: str = "") -> str:
    return f"/api/v1/portal/projects/{wedding['id']}/moodboards{path}"


async def new_board(client: AsyncClient, url: str, **body: Any) -> Any:
    response = await send(client, "POST", url, json={"title": "Overall look", **body})
    assert response.status_code == 201, response.text
    return response.json()


async def add_images(
    client: AsyncClient, url: str, count: int = 1, section_id: str | None = None, **kw: Any
) -> Any:
    files = [
        ("files", (f"idea-{i}.jpg", photo((40 * i % 255, 120, 90)), "image/jpeg"))
        for i in range(count)
    ]
    data = {"section_id": section_id} if section_id else {}
    response = await send(client, "POST", f"{url}/items", files=files, data=data, **kw)
    assert response.status_code == 201, response.text
    return response.json()


async def test_board_from_template_with_processed_images(
    world: World, wedding: dict[str, Any]
) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    assert [s["title"] for s in board["sections"]][:3] == ["Overall look", "Venue", "Flowers"]
    flowers = board["sections"][2]["id"]

    board = await add_images(lead, MB(world, wedding, f"/{board['id']}"), 2, flowers)

    assert len(board["items"]) == 2
    assert all(i["section_id"] == flowers for i in board["items"])
    detail = (await lead.get(MB(world, wedding, f"/{board['id']}"))).json()
    assert all(i["ready"] for i in detail["items"])  # processed after the request committed
    assert detail["item_count"] == 2 and len(detail["preview"]) == 2
    item = detail["items"][0]
    base = MB(world, wedding, f"/{board['id']}/items/{item['id']}/image")

    thumb = await lead.get(base, params={"size": "thumb"})
    display = await lead.get(base, params={"size": "display"})
    original = await lead.get(base, params={"size": "original"})
    assert thumb.headers["content-type"] == "image/webp"
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 400
    assert max(Image.open(io.BytesIO(display.content)).size) == 1200  # never upscaled
    assert "private" in thumb.headers["cache-control"]
    assert original.headers["content-disposition"] == "attachment"
    # Derived versions carry no metadata; the original keeps its GPS data for the team.
    assert dict(Image.open(io.BytesIO(display.content)).getexif()) == {}
    assert 0x8825 in Image.open(io.BytesIO(original.content)).getexif()


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("idea.pdf", b"%PDF-1.7", "unsupported_image"),
        ("idea.jpg", b"not an image at all", "unsupported_image"),
        ("idea.png", None, "unsupported_image"),  # a JPEG named .png
    ],
)
async def test_rejects_non_images(
    world: World, wedding: dict[str, Any], name: str, data: bytes | None, code: str
) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    response = await send(
        lead,
        "POST",
        MB(world, wedding, f"/{board['id']}/items"),
        files=[("files", (name, data or photo(), "application/octet-stream"))],
    )

    assert response.status_code == 422
    assert response.json()["code"] == code


async def test_couple_sees_only_shared_boards_without_internal_notes(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    internal = await new_board(lead, MB(world, wedding), title="Vendor shortlist")
    shared = await new_board(lead, MB(world, wedding), title="Overall look", visibility="client")
    await send(
        lead,
        "PATCH",
        MB(world, wedding, f"/{shared['id']}"),
        json={"notes_internal": "Budget is tight", "palette": ["#C9A9A6", "#4F6354"]},
        headers={"If-Match": f'"{shared["version"]}"'},
    )

    boards = (await couple.get(portal(wedding))).json()
    assert [b["title"] for b in boards] == ["Overall look"]
    detail = (await couple.get(portal(wedding, f"/{shared['id']}"))).json()
    assert "notes_internal" not in detail and "visibility" not in detail
    assert detail["palette"] == ["#c9a9a6", "#4f6354"]
    assert (await couple.get(portal(wedding, f"/{internal['id']}"))).status_code == 404
    assert (await couple.get(MB(world, wedding))).status_code == 403  # planner API stays closed


async def test_couple_uploads_hearts_and_comments(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    shared = await new_board(lead, MB(world, wedding), visibility="client")
    team_board = await add_images(lead, MB(world, wedding, f"/{shared['id']}"))
    team_item = team_board["items"][0]["id"]
    OUTBOX.clear()

    mine = await add_images(couple, portal(wedding, f"/{shared['id']}"))
    own_item = next(i for i in mine["items"] if i["uploaded_by_type"] == "client")
    assert own_item["can_edit"] is True
    assert any(
        e.subject.startswith("New inspiration") for e in OUTBOX if e.to == "member@example.com"
    )

    hearted = await send(couple, "PUT", portal(wedding, f"/{shared['id']}/items/{team_item}/heart"))
    item = next(i for i in hearted.json()["items"] if i["id"] == team_item)
    assert item["hearted_by_me"] is True and item["heart_names"] == ["Mia Becker"]

    comment = await send(
        couple,
        "POST",
        portal(wedding, f"/{shared['id']}/items/{team_item}/comments"),
        json={"body": "Love the peonies!"},
    )
    assert comment.status_code == 201
    listed = (
        await couple.get(portal(wedding, f"/{shared['id']}/items/{team_item}/comments"))
    ).json()
    assert [c["body"] for c in listed] == ["Love the peonies!"]

    # Only the planner selects; the couple only changes their own images.
    status = await send(
        couple,
        "PATCH",
        portal(wedding, f"/{shared['id']}/items/{team_item}"),
        json={"status": "selected"},
    )
    foreign = await send(couple, "DELETE", portal(wedding, f"/{shared['id']}/items/{team_item}"))
    own = await send(couple, "DELETE", portal(wedding, f"/{shared['id']}/items/{own_item['id']}"))
    assert status.status_code == 403
    assert foreign.status_code == 403
    assert own.status_code == 200
    selected = await send(
        lead,
        "PATCH",
        MB(world, wedding, f"/{shared['id']}/items/{team_item}"),
        json={"status": "selected"},
    )
    assert selected.json()["selected_count"] == 1


async def test_couple_boards_stay_shared(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    board = await new_board(couple, portal(wedding), title="Our ideas", visibility="internal")
    assert board["from_couple"] is True and board["can_manage"] is True

    team_view = (await world["member"].client.get(MB(world, wedding, f"/{board['id']}"))).json()
    assert team_view["visibility"] == "client" and team_view["created_by_type"] == "client"
    hide = await send(
        world["member"].client,
        "PATCH",
        MB(world, wedding, f"/{board['id']}"),
        json={"visibility": "internal"},
        headers={"If-Match": f'"{team_view["version"]}"'},
    )
    assert hide.status_code == 409
    palette = await send(
        couple,
        "PATCH",
        portal(wedding, f"/{board['id']}"),
        json={"palette": ["#000000"]},
        headers={"If-Match": f'"{team_view["version"]}"'},
    )
    assert palette.status_code == 403


async def test_roles_and_tenants(world: World, wedding: dict[str, Any]) -> None:
    board = await new_board(world["member"].client, MB(world, wedding))
    path = MB(world, wedding, f"/{board['id']}")
    viewer = world["member2"].client

    assert (await viewer.get(path)).status_code == 200
    blocked = await send(
        viewer, "POST", f"{path}/items", files=[("files", ("a.jpg", photo(), "image/jpeg"))]
    )
    assert blocked.status_code == 403
    assert (await send(viewer, "DELETE", path)).status_code == 403  # admins and leads only
    assert (await world["outsider"].client.get(path)).status_code == 404
    assert (await world["anonymous"].client.get(path)).status_code == 401
    assert (await send(world["org_admin"].client, "DELETE", path)).status_code == 204


async def test_reorder_moves_images_between_sections(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    board = await add_images(lead, MB(world, wedding, f"/{board['id']}"), 2)
    a, b = (i["id"] for i in board["items"])
    cake = next(s["id"] for s in board["sections"] if s["title"] == "Cake")

    response = await send(
        lead,
        "POST",
        MB(world, wedding, f"/{board['id']}/reorder"),
        json={"sections": [], "items": {cake: [b], "": [a]}},
    )

    items = {i["id"]: i["section_id"] for i in response.json()["items"]}
    assert items == {a: None, b: cake}


async def test_comments_on_internal_boards_stay_hidden_from_the_couple(
    world: World, wedding: dict[str, Any], couple: AsyncClient, app_engine: AsyncEngine
) -> None:
    lead = world["member"].client
    internal = await new_board(lead, MB(world, wedding))
    board = await add_images(lead, MB(world, wedding, f"/{internal['id']}"))
    item = board["items"][0]["id"]
    await send(
        lead,
        "POST",
        P(world, wedding, "/comments"),
        json={
            "target_type": "moodboard_item",
            "target_id": item,
            "body": "Too expensive, but show them?",
            "visibility": "client",
        },
    )
    couple_id = (await couple.get("/api/v1/me")).json()["id"]

    async with app_engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true), "
                "set_config('app.role', 'client', true)"
            ),
            {"o": str(world.org_a), "u": couple_id},
        )
        seen = (
            await conn.execute(
                text("SELECT count(*) FROM comments WHERE target_type = 'moodboard_item'")
            )
        ).scalar_one()
        items = (await conn.execute(text("SELECT count(*) FROM moodboard_items"))).scalar_one()
    assert seen == 0 and items == 0
    assert (
        await couple.get(portal(wedding, f"/{internal['id']}/items/{item}/comments"))
    ).status_code == 404


async def test_deleting_removes_files_and_erasure_covers_moodboards(
    world: World, wedding: dict[str, Any]
) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    board = await add_images(lead, MB(world, wedding, f"/{board['id']}"), 2)
    assert len(storage.MEMORY) == 6  # original, thumbnail, display version per image

    await send(
        lead, "DELETE", MB(world, wedding, f"/{board['id']}/items/{board['items'][0]['id']}")
    )
    assert len(storage.MEMORY) == 3

    erased = await send(
        world["org_admin"].client,
        "POST",
        f"/api/v1/orgs/{world.org_a}/clients/{wedding['client_id']}/erase",
        json={"confirm": "Mia & Tom"},
    )
    assert erased.status_code == 200
    assert storage.MEMORY == {}


async def test_client_export_contains_moodboard_images(
    world: World, wedding: dict[str, Any]
) -> None:
    import zipfile

    board = await new_board(world["member"].client, MB(world, wedding))
    await add_images(world["member"].client, MB(world, wedding, f"/{board['id']}"))

    response = await world["org_admin"].client.get(
        f"/api/v1/orgs/{world.org_a}/clients/{wedding['client_id']}/export"
    )

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert any(n.startswith("moodboards/") and n.endswith("idea-0.jpg") for n in archive.namelist())


async def test_pdf_export_for_vendors(
    world: World, wedding: dict[str, Any], owner_engine: AsyncEngine
) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding), title="Flowers for Blütenwerk")
    flowers = next(s["id"] for s in board["sections"] if s["title"] == "Flowers")
    board = await add_images(lead, MB(world, wedding, f"/{board['id']}"), 3, flowers)
    first, second = board["items"][0]["id"], board["items"][1]["id"]
    base = MB(world, wedding, f"/{board['id']}")
    await send(
        lead,
        "PATCH",
        f"{base}/items/{first}",
        json={"status": "selected", "caption": "Peonies, blush"},
    )
    await send(lead, "PATCH", f"{base}/items/{second}", json={"status": "discarded"})

    selected = await world["member2"].client.get(f"{base}/export.pdf")  # viewers may export
    everything = await lead.get(f"{base}/export.pdf", params={"selected_only": False})

    assert selected.status_code == 200
    assert selected.headers["content-type"] == "application/pdf"
    assert selected.content.startswith(b"%PDF")
    assert "attachment" in selected.headers["content-disposition"]
    # One selected image vs. two not-discarded ones: the second PDF is larger.
    assert len(everything.content) > len(selected.content)
    async with owner_engine.begin() as conn:
        exports = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'moodboard.exported'")
            )
        ).scalar_one()
    assert exports == 2
    # The couple cannot export.
    assert (await world["client"].client.get(f"{base}/export.pdf")).status_code == 404
