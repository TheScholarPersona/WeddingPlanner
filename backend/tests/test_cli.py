"""Operator commands (python -m app.cli ...)."""

import pytest
from fastapi import FastAPI

from app import cli
from tests.helpers import accept, new_organization, token_from_link


async def test_create_organization_prints_the_admin_invitation(
    app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    await cli._create_organization("Atelier Nord", "nord@example.com")

    printed = capsys.readouterr().out
    assert "Created organization 'Atelier Nord'" in printed
    admin = await accept(app, token_from_link(printed, "invite"), "Nora Nord")
    me = (await admin.get("/api/v1/me")).json()
    assert [(m["organization_name"], m["role"]) for m in me["memberships"]] == [
        ("Atelier Nord", "org_admin")
    ]


async def test_grant_platform_admin(app: FastAPI, capsys: pytest.CaptureFixture[str]) -> None:
    _, token = await new_organization("Atelier Süd", "sued@example.com")
    client = await accept(app, token, "Sina Süd")

    await cli._grant_platform_admin("SUED@example.com")

    assert "is now a platform admin" in capsys.readouterr().out
    assert (await client.get("/api/v1/me")).json()["is_platform_admin"] is True
    with pytest.raises(SystemExit, match="No account with the email"):
        await cli._grant_platform_admin("nobody@example.com")
