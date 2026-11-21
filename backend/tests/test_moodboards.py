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
    assert hide.json()["code"] == "couple_board"
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


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_board_limit_per_wedding(
    world: World, wedding: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.moodboards import service

    monkeypatch.setattr(service, "MAX_BOARDS_PER_WEDDING", 1)
    lead = world["member"].client
    await new_board(lead, MB(world, wedding))

    response = await send(lead, "POST", MB(world, wedding), json={"title": "One too many"})

    assert response.status_code == 409
    assert response.json()["code"] == "too_many_boards"
    assert len((await lead.get(MB(world, wedding))).json()) == 1


async def test_sections_add_rename_delete(
    world: World, wedding: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    base = MB(world, wedding, f"/{board['id']}")

    added = await send(lead, "POST", f"{base}/sections", json={"title": "Stationery"})
    stationery = next(s for s in added.json()["sections"] if s["title"] == "Stationery")
    renamed = await send(
        lead, "PATCH", f"{base}/sections/{stationery['id']}", json={"title": "Invitations"}
    )
    assert "Invitations" in [s["title"] for s in renamed.json()["sections"]]

    board = await add_images(lead, base, 1, stationery["id"])
    deleted = await send(lead, "DELETE", f"{base}/sections/{stationery['id']}")
    after = deleted.json()
    assert stationery["id"] not in [s["id"] for s in after["sections"]]
    assert [i["section_id"] for i in after["items"]] == [None]  # images move to "Unsorted"

    from app.moodboards import service

    monkeypatch.setattr(service, "MAX_SECTIONS_PER_BOARD", len(after["sections"]))
    full = await send(lead, "POST", f"{base}/sections", json={"title": "Favors"})
    assert full.status_code == 409
    assert full.json()["code"] == "too_many_sections"


async def test_couple_adds_sections_only_to_own_boards(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    team = await new_board(world["member"].client, MB(world, wedding), visibility="client")
    own = await new_board(couple, portal(wedding), title="Our ideas")

    blocked = await send(
        couple, "POST", portal(wedding, f"/{team['id']}/sections"), json={"title": "Shoes"}
    )
    added = await send(
        couple, "POST", portal(wedding, f"/{own['id']}/sections"), json={"title": "Shoes"}
    )

    assert blocked.status_code == 403
    assert "Shoes" in [s["title"] for s in added.json()["sections"]]


async def test_image_limits(
    world: World, wedding: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.moodboards import images, service

    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    base = MB(world, wedding, f"/{board['id']}")
    await add_images(lead, base, 2)

    monkeypatch.setattr(service, "MAX_ITEMS_PER_WEDDING", 2)
    full = await send(
        lead, "POST", f"{base}/items", files=[("files", ("c.jpg", photo(), "image/jpeg"))]
    )
    assert full.status_code == 409
    assert full.json()["code"] == "too_many_images"

    monkeypatch.setattr(service, "MAX_ITEMS_PER_WEDDING", 300)
    monkeypatch.setattr(images, "MAX_IMAGE_MB", 0)
    large = await send(
        lead, "POST", f"{base}/items", files=[("files", ("d.jpg", photo(), "image/jpeg"))]
    )
    assert large.status_code == 413
    assert large.json()["code"] == "file_too_large"
    assert (await lead.get(base)).json()["item_count"] == 2


async def test_caption_and_section_of_an_image(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    cake = next(s["id"] for s in board["sections"] if s["title"] == "Cake")
    base = MB(world, wedding, f"/{board['id']}")
    item = (await add_images(lead, base))["items"][0]["id"]

    moved = await send(
        lead, "PATCH", f"{base}/items/{item}", json={"caption": "Naked cake", "section_id": cake}
    )
    assert moved.json()["items"][0]["caption"] == "Naked cake"
    assert moved.json()["items"][0]["section_id"] == cake

    unsorted = await send(lead, "PATCH", f"{base}/items/{item}", json={"move_to_unsorted": True})
    assert unsorted.json()["items"][0]["section_id"] is None


async def test_team_hearts_and_takes_them_back(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding))
    base = MB(world, wedding, f"/{board['id']}")
    item = (await add_images(lead, base))["items"][0]["id"]

    hearted = (await send(lead, "PUT", f"{base}/items/{item}/heart")).json()["items"][0]
    assert hearted["hearted_by_me"] is True and hearted["heart_names"] == ["Max Member"]

    undone = (await send(lead, "DELETE", f"{base}/items/{item}/heart")).json()["items"][0]
    assert undone["hearted_by_me"] is False and undone["heart_names"] == []


async def test_couple_takes_a_heart_back(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    board = await new_board(world["member"].client, MB(world, wedding), visibility="client")
    item = (await add_images(world["member"].client, MB(world, wedding, f"/{board['id']}")))[
        "items"
    ][0]["id"]
    heart = portal(wedding, f"/{board['id']}/items/{item}/heart")
    await send(couple, "PUT", heart)

    undone = (await send(couple, "DELETE", heart)).json()["items"][0]

    assert undone["hearted_by_me"] is False and undone["heart_names"] == []


async def test_couple_gets_display_versions_but_not_originals(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    board = await new_board(world["member"].client, MB(world, wedding), visibility="client")
    item = (await add_images(world["member"].client, MB(world, wedding, f"/{board['id']}")))[
        "items"
    ][0]["id"]
    image = portal(wedding, f"/{board['id']}/items/{item}/image")

    display = await couple.get(image, params={"size": "display"})
    original = await couple.get(image, params={"size": "original"})

    assert display.headers["content-type"] == "image/webp"
    assert dict(Image.open(io.BytesIO(display.content)).getexif()) == {}  # no GPS data
    assert original.status_code == 422


async def test_couple_arranges_only_own_boards(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    team = await new_board(world["member"].client, MB(world, wedding), visibility="client")
    own = await new_board(couple, portal(wedding), title="Our ideas")
    own = await add_images(couple, portal(wedding, f"/{own['id']}"))
    item = own["items"][0]["id"]
    venue = next(s["id"] for s in own["sections"] if s["title"] == "Venue")

    blocked = await send(
        couple,
        "POST",
        portal(wedding, f"/{team['id']}/reorder"),
        json={"sections": [], "items": {}},
    )
    moved = await send(
        couple,
        "POST",
        portal(wedding, f"/{own['id']}/reorder"),
        json={"sections": [], "items": {venue: [item]}},
    )

    assert blocked.status_code == 403
    assert moved.json()["items"][0]["section_id"] == venue


async def test_couple_deletes_own_boards_only(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    team = await new_board(world["member"].client, MB(world, wedding), visibility="client")
    own = await new_board(couple, portal(wedding), title="Our ideas")
    await add_images(couple, portal(wedding, f"/{own['id']}"))

    blocked = await send(couple, "DELETE", portal(wedding, f"/{team['id']}"))
    deleted = await send(couple, "DELETE", portal(wedding, f"/{own['id']}"))

    assert blocked.status_code == 403
    assert deleted.status_code == 204
    assert [b["title"] for b in (await couple.get(portal(wedding))).json()] == ["Overall look"]
    assert storage.MEMORY == {}  # the board's images are gone too


async def test_team_only_comments_stay_hidden_on_shared_boards(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    board = await new_board(lead, MB(world, wedding), visibility="client")
    item = (await add_images(lead, MB(world, wedding, f"/{board['id']}")))["items"][0]["id"]
    for body, visibility in (("Shall we show the peonies?", "internal"), ("Peonies?", "client")):
        await send(
            lead,
            "POST",
            P(world, wedding, "/comments"),
            json={
                "target_type": "moodboard_item",
                "target_id": item,
                "body": body,
                "visibility": visibility,
            },
        )

    team = await lead.get(
        P(world, wedding, "/comments"),
        params={"target_type": "moodboard_item", "target_id": item},
    )
    seen = await couple.get(portal(wedding, f"/{board['id']}/items/{item}/comments"))

    assert sorted(c["body"] for c in team.json()) == ["Peonies?", "Shall we show the peonies?"]
    assert [c["body"] for c in seen.json()] == ["Peonies?"]
