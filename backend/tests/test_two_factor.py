"""Two-factor authentication: setup, sign-in with code or recovery code, organization policy."""

import time
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pyotp.totp import TOTP
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import new_client
from tests.helpers import PASSWORD, World, build_world, send


@pytest.fixture
async def world(app: FastAPI) -> World:
    return await build_world(app)


async def reauth(client: AsyncClient) -> None:
    response = await send(client, "POST", "/api/v1/auth/reauth", json={"password": PASSWORD})
    assert response.status_code == 204


async def turn_on(client: AsyncClient) -> tuple[TOTP, list[str]]:
    await reauth(client)
    setup = (await send(client, "POST", "/api/v1/me/2fa/setup")).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert setup["qr_svg"].startswith("data:image/svg+xml")
    totp = TOTP(setup["secret"])
    enabled = await send(client, "POST", "/api/v1/me/2fa/enable", json={"code": totp.now()})
    assert enabled.status_code == 200, enabled.text
    return totp, enabled.json()["recovery_codes"]


def next_code(totp: TOTP) -> str:
    """The next time step's code: the current one was used up when 2FA was switched on."""
    return str(totp.at(time.time() + 30))


async def login(app: FastAPI, email: str) -> tuple[AsyncClient, Any]:
    client = new_client(app)
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()


async def test_setup_needs_a_recent_password_confirmation(world: World) -> None:
    member = world["member"].client
    # Sessions start with a fresh confirmation; age it.
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        await db.execute(text("UPDATE sessions SET reauth_at = now() - interval '1 hour'"))
        await db.commit()

    response = await send(member, "POST", "/api/v1/me/2fa/setup")

    assert response.status_code == 403
    assert response.json()["code"] == "reauth_required"


async def test_sign_in_with_code(app: FastAPI, world: World, owner_engine: AsyncEngine) -> None:
    totp, codes = await turn_on(world["member"].client)
    assert len(codes) == 10
    assert (await world["member"].client.get("/api/v1/me")).json()["two_factor_enabled"] is True

    client, body = await login(app, "member@example.com")
    assert body == {"two_factor_required": True}
    # The half-finished session cannot reach anything else.
    blocked = await client.get("/api/v1/me")
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "two_factor_pending"
    assert (await client.get(f"/api/v1/orgs/{world.org_a}/members")).json()[
        "code"
    ] == "two_factor_pending"

    wrong = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": "000000"})
    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_code"
    ok = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": next_code(totp)})
    assert ok.status_code == 200
    assert ok.json()["email"] == "member@example.com"
    assert (await client.get("/api/v1/me")).status_code == 200

    async with owner_engine.begin() as conn:
        secret = (
            await conn.execute(
                text("SELECT totp_secret_enc FROM users WHERE email = 'member@example.com'")
            )
        ).scalar_one()
    assert totp.secret not in secret  # stored encrypted


async def test_recovery_codes_work_once(app: FastAPI, world: World) -> None:
    _, codes = await turn_on(world["member"].client)

    client, _ = await login(app, "member@example.com")
    used = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": codes[0].upper()})
    assert used.status_code == 200

    again, _ = await login(app, "member@example.com")
    reused = await send(again, "POST", "/api/v1/auth/2fa/verify", json={"code": codes[0]})
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_code"
    status = (await client.get("/api/v1/me/2fa")).json()
    assert status["recovery_codes_left"] == 9


async def test_too_many_wrong_codes_end_the_attempt(app: FastAPI, world: World) -> None:
    await turn_on(world["member"].client)
    client, _ = await login(app, "member@example.com")

    for _ in range(4):
        r = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": "111111"})
        assert r.status_code == 400
    last = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": "111111"})

    assert last.status_code == 401
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_invitation_acceptance_does_not_skip_the_second_factor(
    app: FastAPI, world: World
) -> None:
    from app.organizations.models import OrgRole
    from tests.helpers import invite_directly

    await turn_on(world["member"].client)
    token = await invite_directly(world.org_b, "member@example.com", OrgRole.MEMBER)
    client = new_client(app)
    response = await client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"password": PASSWORD}
    )

    assert response.json() == {"two_factor_required": True}
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_disable_needs_password_and_code(world: World) -> None:
    member = world["member"].client
    totp, _ = await turn_on(member)

    wrong = await send(
        member, "POST", "/api/v1/me/2fa/disable", json={"password": "nope", "code": totp.now()}
    )
    ok = await send(
        member,
        "POST",
        "/api/v1/me/2fa/disable",
        json={"password": PASSWORD, "code": next_code(totp)},
    )

    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_current_password"
    assert ok.status_code == 204
    assert (await member.get("/api/v1/me")).json()["two_factor_enabled"] is False


async def test_organization_can_require_two_factor(world: World) -> None:
    admin = world["org_admin"].client
    path = f"/api/v1/orgs/{world.org_a}"

    refused = await send(admin, "PATCH", path, json={"require_2fa": True})
    assert refused.status_code == 409
    assert refused.json()["code"] == "enable_own_2fa_first"

    await turn_on(admin)
    assert (await send(admin, "PATCH", path, json={"require_2fa": True})).status_code == 200

    blocked = await world["member"].client.get(f"{path}/members")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "two_factor_required"
    # Couples are not affected, and the member can still reach their account to set it up.
    assert (await world["client"].client.get("/api/v1/portal/projects")).status_code == 200
    assert (await world["member"].client.get("/api/v1/me/2fa")).status_code == 200
    await turn_on(world["member"].client)
    assert (await world["member"].client.get(f"{path}/members")).status_code == 200


async def test_a_code_works_only_once(app: FastAPI, world: World) -> None:
    totp, _ = await turn_on(world["member"].client)
    code = next_code(totp)

    first, _ = await login(app, "member@example.com")
    assert (
        await send(first, "POST", "/api/v1/auth/2fa/verify", json={"code": code})
    ).status_code == 200
    second, _ = await login(app, "member@example.com")
    replay = await send(second, "POST", "/api/v1/auth/2fa/verify", json={"code": code})

    assert replay.status_code == 400


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_cancelling_the_code_step_ends_the_half_finished_session(
    app: FastAPI, world: World
) -> None:
    totp, _ = await turn_on(world["member"].client)
    client, _ = await login(app, "member@example.com")

    cancelled = await send(client, "POST", "/api/v1/auth/2fa/cancel")
    later = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": next_code(totp)})

    assert cancelled.status_code == 204
    assert later.status_code == 401
    assert later.json()["code"] == "not_authenticated"  # no longer waiting for a code


async def test_new_recovery_codes_replace_the_old_ones(app: FastAPI, world: World) -> None:
    member = world["member"].client
    _, old_codes = await turn_on(member)

    fresh = await send(member, "POST", "/api/v1/me/2fa/recovery-codes")
    new_codes = fresh.json()["recovery_codes"]
    assert len(new_codes) == 10 and not set(new_codes) & set(old_codes)

    client, _ = await login(app, "member@example.com")
    old = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": old_codes[0]})
    new = await send(client, "POST", "/api/v1/auth/2fa/verify", json={"code": new_codes[0]})
    assert old.status_code == 400
    assert new.status_code == 200


async def test_platform_admins_cannot_turn_off_two_factor(
    world: World, owner_engine: AsyncEngine
) -> None:
    member = world["member"].client
    totp, _ = await turn_on(member)
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET is_platform_admin = true WHERE email = 'member@example.com'")
        )

    response = await send(
        member,
        "POST",
        "/api/v1/me/2fa/disable",
        json={"password": PASSWORD, "code": next_code(totp)},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "two_factor_mandatory"
    assert (await member.get("/api/v1/me")).json()["two_factor_enabled"] is True
