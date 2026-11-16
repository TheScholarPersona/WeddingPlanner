"""Documents: upload checks, versions, sharing with the couple, virus scan, access rules."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.documents import scanner, storage
from tests.helpers import World, send
from tests.test_budget_portal import COUPLE
from tests.test_budget_portal import couple as couple
from tests.test_tasks import P
from tests.test_tasks import wedding as wedding
from tests.test_tasks import world as world

PDF = b"%PDF-1.7\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


async def upload(
    client: AsyncClient,
    world: World,
    wedding: dict[str, Any],
    name: str = "Venue contract.pdf",
    data: bytes = PDF,
    **form: str,
) -> Any:
    return await send(
        client,
        "POST",
        P(world, wedding, "/documents"),
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )


def portal(wedding: dict[str, Any], path: str = "") -> str:
    return f"/api/v1/portal/projects/{wedding['id']}{path}"


async def test_upload_list_and_download(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    response = await upload(lead, world, wedding, category="contract", title="Venue contract")

    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["title"] == "Venue contract"
    assert doc["category"] == "contract"
    assert doc["visibility"] == "internal"
    assert doc["current"]["filename"] == "Venue contract.pdf"
    assert doc["current"]["content_type"] == "application/pdf"
    assert doc["current"]["scan_status"] == "not_scanned"
    assert doc["current"]["downloadable"] is True
    assert len(storage.MEMORY) == 1
    assert next(iter(storage.MEMORY)).startswith(f"orgs/{world.org_a}/projects/{wedding['id']}/")

    listed = (await lead.get(P(world, wedding, "/documents"))).json()
    assert [d["id"] for d in listed] == [doc["id"]]

    file = await lead.get(P(world, wedding, f"/documents/{doc['id']}/download"))
    assert file.status_code == 200
    assert file.content == PDF
    assert file.headers["content-type"] == "application/pdf"
    assert file.headers["content-disposition"].startswith("attachment;")
    assert file.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in file.headers["content-security-policy"]


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("invoice.exe", b"MZ\x90\x00", "unsupported_file"),
        ("invoice.pdf", b"MZ\x90\x00 not a pdf", "unsupported_file"),
        ("photo.png", PDF, "unsupported_file"),
        ("empty.pdf", b"", "unsupported_file"),
    ],
)
async def test_rejects_unsupported_or_disguised_files(
    world: World, wedding: dict[str, Any], name: str, data: bytes, code: str
) -> None:
    response = await upload(world["member"].client, world, wedding, name=name, data=data)

    assert response.status_code == 422
    assert response.json()["code"] == code
    assert storage.MEMORY == {}


async def test_rejects_files_above_the_size_limit(
    world: World, wedding: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    big = PDF + b"0" * (1024 * 1024)

    response = await upload(world["member"].client, world, wedding, data=big)

    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"


async def test_file_names_are_sanitized(world: World, wedding: dict[str, Any]) -> None:
    response = await upload(
        world["member"].client, world, wedding, name="../../etc/Vertrag: Schloß?.pdf"
    )

    assert response.status_code == 201
    assert response.json()["current"]["filename"] == "Vertrag Schloß.pdf"
    file = await world["member"].client.get(
        P(world, wedding, f"/documents/{response.json()['id']}/download")
    )
    assert "filename*=UTF-8''Vertrag%20Schlo%C3%9F.pdf" in file.headers["content-disposition"]


def test_safe_filename_strips_paths_and_control_characters() -> None:
    from app.documents.files import safe_filename

    assert safe_filename('C:\\Users\\x\\"Menu"\x07\n.pdf') == "Menu.pdf"
    assert safe_filename("...") == "file"
    assert safe_filename(None) == "file"
    assert len(safe_filename("a" * 300 + ".pdf")) == 200
    assert safe_filename("a" * 300 + ".pdf").endswith(".pdf")


async def test_versions_keep_history(world: World, wedding: dict[str, Any]) -> None:
    lead = world["member"].client
    doc = (await upload(lead, world, wedding)).json()

    response = await send(
        lead,
        "POST",
        P(world, wedding, f"/documents/{doc['id']}/versions"),
        files={"file": ("Venue contract v2.pdf", PDF + b"%v2", "application/pdf")},
    )

    assert response.status_code == 201, response.text
    detail = response.json()
    assert detail["version_count"] == 2
    assert detail["current"]["number"] == 2
    assert [v["number"] for v in detail["versions"]] == [2, 1]
    old = await lead.get(
        P(world, wedding, f"/documents/{doc['id']}/download"),
        params={"version": detail["versions"][1]["id"]},
    )
    assert old.content == PDF


async def test_viewers_read_but_cannot_change(world: World, wedding: dict[str, Any]) -> None:
    doc = (await upload(world["member"].client, world, wedding)).json()
    viewer = world["member2"].client

    assert (await viewer.get(P(world, wedding, "/documents"))).status_code == 200
    assert (await upload(viewer, world, wedding)).status_code == 403
    assert (
        await send(viewer, "DELETE", P(world, wedding, f"/documents/{doc['id']}"))
    ).status_code == 403


async def test_other_tenants_and_weddings_cannot_reach_documents(
    world: World, wedding: dict[str, Any], app_engine: AsyncEngine
) -> None:
    doc = (await upload(world["member"].client, world, wedding)).json()
    download = P(world, wedding, f"/documents/{doc['id']}/download")

    assert (await world["outsider"].client.get(download)).status_code == 404
    assert (await world["anonymous"].client.get(download)).status_code == 401
    # The organization's client login is not on this wedding.
    assert (await world["client"].client.get(download)).status_code == 404

    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.org_id', :o, true)"), {"o": str(world.org_b)}
        )
        rows = (await conn.execute(text("SELECT count(*) FROM document_versions"))).scalar_one()
    assert rows == 0


async def test_sharing_with_the_couple(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    lead = world["member"].client
    internal = (await upload(lead, world, wedding, title="Internal calculation")).json()
    shared = (await upload(lead, world, wedding, title="Menu", visibility="client")).json()

    listed = (await couple.get(portal(wedding, "/documents"))).json()
    assert [d["title"] for d in listed] == ["Menu"]
    assert "visibility" not in listed[0]
    assert (await couple.get(portal(wedding, f"/documents/{shared['id']}/download"))).content == PDF
    hidden = await couple.get(portal(wedding, f"/documents/{internal['id']}/download"))
    assert hidden.status_code == 404
    # The planner API stays closed to couples.
    assert (await couple.get(P(world, wedding, "/documents"))).status_code == 403

    unshare = await send(
        lead,
        "PATCH",
        P(world, wedding, f"/documents/{shared['id']}"),
        json={"visibility": "internal"},
        headers={"If-Match": f'"{shared["version"]}"'},
    )
    assert unshare.status_code == 200
    assert (await couple.get(portal(wedding, "/documents"))).json() == []


async def test_couples_upload_and_delete_only_their_own(
    world: World, wedding: dict[str, Any], couple: AsyncClient
) -> None:
    team_doc = (await upload(world["member"].client, world, wedding, visibility="client")).json()
    response = await send(
        couple,
        "POST",
        portal(wedding, "/documents"),
        files={"file": ("Moodboard.png", PNG, "image/png")},
        data={"title": "Moodboard"},
    )

    assert response.status_code == 201, response.text
    mine = next(d for d in response.json() if d["title"] == "Moodboard")
    assert mine["from_couple"] is True
    assert mine["can_delete"] is True
    team_view = (await world["member"].client.get(P(world, wedding, "/documents"))).json()
    assert {d["title"]: d["uploaded_by_type"] for d in team_view}["Moodboard"] == "client"
    assert {d["title"]: d["visibility"] for d in team_view}["Moodboard"] == "client"

    blocked = await send(couple, "DELETE", portal(wedding, f"/documents/{team_doc['id']}"))
    assert blocked.status_code == 404
    deleted = await send(couple, "DELETE", portal(wedding, f"/documents/{mine['id']}"))
    assert deleted.status_code == 204
    assert len(storage.MEMORY) == 1


async def test_delete_removes_files_and_is_audited(
    world: World, wedding: dict[str, Any], owner_engine: AsyncEngine
) -> None:
    lead = world["member"].client
    doc = (await upload(lead, world, wedding)).json()

    response = await send(lead, "DELETE", P(world, wedding, f"/documents/{doc['id']}"))

    assert response.status_code == 204
    assert storage.MEMORY == {}
    assert (await lead.get(P(world, wedding, "/documents"))).json() == []
    async with owner_engine.begin() as conn:
        actions = (
            (
                await conn.execute(
                    text(
                        "SELECT action FROM audit_log WHERE resource_id = :id ORDER BY created_at"
                    ),
                    {"id": doc["id"]},
                )
            )
            .scalars()
            .all()
        )
    assert actions == ["document.uploaded", "document.deleted"]


# --- Virus scan ----------------------------------------------------------------------------


@pytest.fixture
def scanning(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    """Turn scanning on with a fake ClamAV that flags files containing 'EICAR'."""
    monkeypatch.setattr(get_settings(), "virus_scan", "clamav")
    seen: list[bytes] = []

    async def fake_scan(data: bytes) -> scanner.ScanResult:
        seen.append(data)
        if b"BROKEN" in data:
            raise scanner.ScanError("clamd down")
        return "infected" if b"EICAR" in data else "clean"

    monkeypatch.setattr(scanner, "scan_bytes", fake_scan)
    return seen


async def test_clean_files_become_downloadable_after_the_scan(
    world: World, wedding: dict[str, Any], scanning: list[bytes]
) -> None:
    lead = world["member"].client
    doc = (await upload(lead, world, wedding)).json()

    # The upload response is created before the scan runs after the response.
    assert doc["current"]["scan_status"] == "pending"
    assert doc["current"]["downloadable"] is False
    assert scanning == [PDF]
    detail = (await lead.get(P(world, wedding, f"/documents/{doc['id']}"))).json()
    assert detail["current"]["scan_status"] == "clean"
    assert (await lead.get(P(world, wedding, f"/documents/{doc['id']}/download"))).content == PDF


async def test_infected_files_are_removed_and_blocked(
    world: World, wedding: dict[str, Any], scanning: list[bytes], owner_engine: AsyncEngine
) -> None:
    lead = world["member"].client
    doc = (await upload(lead, world, wedding, data=PDF + b"EICAR")).json()

    detail = (await lead.get(P(world, wedding, f"/documents/{doc['id']}"))).json()
    blocked = await lead.get(P(world, wedding, f"/documents/{doc['id']}/download"))

    assert detail["current"]["scan_status"] == "infected"
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "file_infected"
    assert storage.MEMORY == {}
    async with owner_engine.begin() as conn:
        actions = (
            (
                await conn.execute(
                    text("SELECT action FROM audit_log WHERE resource_id = :id"), {"id": doc["id"]}
                )
            )
            .scalars()
            .all()
        )
    assert "document.virus_found" in actions


async def test_failed_scans_block_the_download(
    world: World, wedding: dict[str, Any], scanning: list[bytes]
) -> None:
    lead = world["member"].client
    doc = (await upload(lead, world, wedding, data=PDF + b"BROKEN")).json()

    blocked = await lead.get(P(world, wedding, f"/documents/{doc['id']}/download"))

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "file_failed"


async def test_clamd_protocol() -> None:
    """The INSTREAM client against a minimal fake clamd."""
    import asyncio
    import struct

    received = bytearray()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        assert await reader.readexactly(10) == b"zINSTREAM\0"
        while True:
            (size,) = struct.unpack("!L", await reader.readexactly(4))
            if size == 0:
                break
            received.extend(await reader.readexactly(size))
        found = b"EICAR" in received
        writer.write(b"stream: Eicar-Signature FOUND\0" if found else b"stream: OK\0")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    settings = get_settings()
    old = (settings.clamav_host, settings.clamav_port)
    settings.clamav_host, settings.clamav_port = "127.0.0.1", port
    try:
        assert await scanner.scan_bytes(b"x" * 200_000) == "clean"
        assert len(received) == 200_000
        received.clear()
        assert await scanner.scan_bytes(b"...EICAR...") == "infected"
        settings.clamav_port = 1
        with pytest.raises(scanner.ScanError):
            await scanner.scan_bytes(b"x")
    finally:
        settings.clamav_host, settings.clamav_port = old
        server.close()


async def test_couple_notified_when_a_document_is_shared(
    world: World, wedding: dict[str, Any], couple: AsyncClient, app: FastAPI
) -> None:
    from app.notifications.mailer import OUTBOX

    OUTBOX.clear()
    await upload(world["member"].client, world, wedding, title="Seating plan", visibility="client")

    emails = [e for e in OUTBOX if e.to == COUPLE]
    assert len(emails) == 1
    assert emails[0].subject == "New document: Seating plan"
    assert "/portal/files" in emails[0].text


def test_unreachable_scanner_is_retried_in_the_worker() -> None:
    assert scanner.retry_later({"job_try": 1, "max_tries": 3}) is True
    assert scanner.retry_later({"job_try": 3, "max_tries": 3}) is False
    assert scanner.retry_later({}) is False  # inline runs (tests) fail at once
