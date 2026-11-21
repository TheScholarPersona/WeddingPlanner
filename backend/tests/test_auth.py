from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.notifications.mailer import OUTBOX
from tests.conftest import new_client
from tests.helpers import (
    PASSWORD,
    accept,
    last_email_to,
    new_organization,
    send,
    token_from_link,
)

ADMIN = "admin@example.com"


async def _signed_up(app: FastAPI) -> AsyncClient:
    _, token = await new_organization("Atelier Test", ADMIN)
    return await accept(app, token, "Ada Admin")


async def _login(client: AsyncClient, password: str = PASSWORD, email: str = ADMIN) -> int:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.status_code


async def test_accepting_an_invitation_creates_account_membership_and_session(app: FastAPI) -> None:
    client = await _signed_up(app)

    me = await client.get("/api/v1/me")

    assert me.status_code == 200
    body = me.json()
    assert body["email"] == ADMIN
    assert [m["role"] for m in body["memberships"]] == ["org_admin"]
    assert body["memberships"][0]["organization_name"] == "Atelier Test"


async def test_login_sets_hardened_cookies(app: FastAPI) -> None:
    await _signed_up(app)
    client = new_client(app)

    response = await client.post("/api/v1/auth/login", json={"email": ADMIN, "password": PASSWORD})

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("__Host-session="))
    csrf_cookie = next(c for c in cookies if c.startswith("__Host-csrf="))
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/"):
        assert flag.lower() in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()


async def test_wrong_password_and_unknown_email_look_identical(app: FastAPI) -> None:
    await _signed_up(app)
    client = new_client(app)

    wrong = await client.post("/api/v1/auth/login", json={"email": ADMIN, "password": "nope"})
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["code"] == "invalid_credentials"


async def test_account_locks_after_repeated_failures(app: FastAPI, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    await _signed_up(app)
    settings = get_settings()
    monkeypatch.setattr(settings, "max_failed_logins", 3)
    monkeypatch.setattr(settings, "login_rate_limit_per_minute", 100)
    client = new_client(app)

    for _ in range(3):
        assert await _login(client, "wrong password") == 401

    assert await _login(client) == 401  # locked, even with the right password


async def test_login_is_rate_limited(app: FastAPI) -> None:
    client = new_client(app)
    statuses = [await _login(client, "x", "someone@example.com") for _ in range(6)]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


async def test_logout_ends_the_session(app: FastAPI) -> None:
    client = await _signed_up(app)

    assert (await send(client, "POST", "/api/v1/auth/logout")).status_code == 204
    after = await client.get("/api/v1/me")
    assert after.status_code == 401
    assert after.json()["code"] == "not_authenticated"


async def test_state_changing_requests_need_the_csrf_header(app: FastAPI) -> None:
    client = await _signed_up(app)

    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


async def test_password_reset_flow(app: FastAPI) -> None:
    old_session = await _signed_up(app)
    client = new_client(app)

    forgot = await client.post("/api/v1/auth/password/forgot", json={"email": ADMIN})
    token = token_from_link(last_email_to(ADMIN), "reset-password")
    reset = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "password": "a brand new password"}
    )
    reused = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "password": "another new password"}
    )

    assert forgot.status_code == 202
    assert reset.status_code == 204
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_token"
    assert (await old_session.get("/api/v1/me")).status_code == 401
    assert await _login(client, "a brand new password") == 200


async def test_password_reset_for_unknown_email_sends_nothing(app: FastAPI) -> None:
    client = new_client(app)

    response = await client.post("/api/v1/auth/password/forgot", json={"email": "no@example.com"})

    assert response.status_code == 202
    assert OUTBOX == []


async def test_invitation_can_be_used_only_once(app: FastAPI) -> None:
    _, token = await new_organization("Atelier Test", ADMIN)
    await accept(app, token, "Ada Admin")
    client = new_client(app)

    info = await client.get(f"/api/v1/auth/invitations/{token}")
    again = await client.post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "X", "password": PASSWORD}
    )

    assert info.status_code == 404
    assert again.status_code == 404


async def test_expired_invitation_is_rejected(app: FastAPI, owner_engine: AsyncEngine) -> None:
    _, token = await new_organization("Atelier Test", ADMIN)
    async with owner_engine.begin() as conn:
        await conn.execute(
            text("UPDATE invitations SET expires_at = :t"),
            {"t": datetime.now(UTC) - timedelta(minutes=1)},
        )

    response = await new_client(app).get(f"/api/v1/auth/invitations/{token}")

    assert response.status_code == 404
    assert response.json()["code"] == "invitation_invalid"


async def test_existing_account_must_confirm_its_password_to_join(app: FastAPI) -> None:
    await _signed_up(app)
    _, second = await new_organization("Second Agency", ADMIN)
    client = new_client(app)

    info = await client.get(f"/api/v1/auth/invitations/{second}")
    wrong = await client.post(
        f"/api/v1/auth/invitations/{second}/accept", json={"password": "not my password"}
    )
    right = await client.post(
        f"/api/v1/auth/invitations/{second}/accept", json={"password": PASSWORD}
    )

    assert info.json()["account_exists"] is True
    assert wrong.status_code == 401
    assert right.status_code == 200
    assert len(right.json()["memberships"]) == 2


async def test_new_account_needs_a_long_password(app: FastAPI) -> None:
    _, token = await new_organization("Atelier Test", ADMIN)

    response = await new_client(app).post(
        f"/api/v1/auth/invitations/{token}/accept", json={"full_name": "Ada", "password": "short"}
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "password"


async def test_changing_password_signs_out_other_sessions(app: FastAPI) -> None:
    first = await _signed_up(app)
    second = new_client(app)
    assert await _login(second) == 200

    wrong = await send(
        first,
        "POST",
        "/api/v1/me/password",
        json={"current_password": "nope", "new_password": "an even better password"},
    )
    right = await send(
        first,
        "POST",
        "/api/v1/me/password",
        json={"current_password": PASSWORD, "new_password": "an even better password"},
    )

    assert wrong.status_code == 400
    assert wrong.json()["code"] == "invalid_current_password"
    assert right.status_code == 204
    assert (await first.get("/api/v1/me")).status_code == 200
    assert (await second.get("/api/v1/me")).status_code == 401


# --- Added for the feature catalog: criteria that had no test yet -------------------------


async def test_profile_name_can_be_changed_and_is_audited(
    app: FastAPI, owner_engine: AsyncEngine
) -> None:
    client = await _signed_up(app)

    updated = await send(client, "PATCH", "/api/v1/me", json={"full_name": "  Ada Lovelace "})

    assert updated.json()["full_name"] == "Ada Lovelace"
    assert (await client.get("/api/v1/me")).json()["full_name"] == "Ada Lovelace"
    async with owner_engine.begin() as conn:
        actions = (
            (await conn.execute(text("SELECT action FROM audit_log WHERE action = 'user.updated'")))
            .scalars()
            .all()
        )
    assert actions == ["user.updated"]


async def test_reauth_with_a_wrong_password_is_refused_and_audited(
    app: FastAPI, owner_engine: AsyncEngine
) -> None:
    client = await _signed_up(app)

    wrong = await send(client, "POST", "/api/v1/auth/reauth", json={"password": "not it"})
    right = await send(client, "POST", "/api/v1/auth/reauth", json={"password": PASSWORD})

    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_credentials"
    assert right.status_code == 204
    async with owner_engine.begin() as conn:
        failed = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'auth.reauth_failed'")
            )
        ).scalar_one()
    assert failed == 1
