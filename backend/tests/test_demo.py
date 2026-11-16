"""The demo organization can be created and its logins work."""

from fastapi import FastAPI

from tests.conftest import new_client


async def test_seed_demo(app: FastAPI, database_urls: dict[str, str]) -> None:
    from app.demo import seed_demo

    result = await seed_demo("Demo Test")

    assert result["admin_email"].endswith("@example.com")
    planner = new_client(app)
    login = await planner.post(
        "/api/v1/auth/login",
        json={"email": result["planner_email"], "password": result["planner_password"]},
    )
    assert login.status_code == 200
    org = login.json()["memberships"][0]["organization_id"]
    weddings = (await planner.get(f"/api/v1/orgs/{org}/projects")).json()
    assert {w["title"] for w in weddings} == {"Lena & Jonas", "Sophie & Amir", "Clara & Max"}

    couple = new_client(app)
    await couple.post(
        "/api/v1/auth/login",
        json={"email": result["couple_email"], "password": result["couple_password"]},
    )
    project = (await couple.get("/api/v1/portal/projects")).json()[0]
    files = (await couple.get(f"/api/v1/portal/projects/{project['id']}/documents")).json()
    assert [f["title"] for f in files] == ["Timeline for the day"]
