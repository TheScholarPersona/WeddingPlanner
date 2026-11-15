"""Test fixtures: a real PostgreSQL 17 in a container, migrated, with the production roles.

Tests use generated data only (see tests/factories.py). Never put real customer data here.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.core.config import get_settings
from app.db.session import dispose_engine

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER = "wedding_owner"
APP_ROLE_PASSWORD = "test-app-password"
ADMIN_ROLE_PASSWORD = "test-admin-password"


def _alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.attributes["database_url"] = url
    return cfg


async def _create_roles(owner_url: str) -> None:
    engine = create_async_engine(owner_url)
    async with engine.begin() as conn:
        for role, password in (("app_user", APP_ROLE_PASSWORD), ("admin_api", ADMIN_ROLE_PASSWORD)):
            await conn.execute(
                text(
                    f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS "
                    f"PASSWORD '{password}'"
                )
            )
    await engine.dispose()


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        "postgres:17-alpine",
        username=OWNER,
        password="test-owner-password",
        dbname="weddingplanner",
        driver="asyncpg",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def database_urls(postgres: PostgresContainer) -> Iterator[dict[str, str]]:
    owner_url = postgres.get_connection_url()
    host = postgres.get_container_host_ip()
    port = postgres.get_exposed_port(5432)
    app_url = f"postgresql+asyncpg://app_user:{APP_ROLE_PASSWORD}@{host}:{port}/weddingplanner"

    asyncio.run(_create_roles(owner_url))
    command.upgrade(_alembic_config(owner_url), "head")

    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = app_url
    os.environ["MIGRATION_DATABASE_URL"] = owner_url
    get_settings.cache_clear()
    yield {"owner": owner_url, "app": app_url}
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def alembic_config(database_urls: dict[str, str]) -> Config:
    return _alembic_config(database_urls["owner"])


@pytest.fixture
async def owner_engine(database_urls: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_urls["owner"])
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engine(database_urls: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_urls["app"])
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(database_urls: dict[str, str]) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await dispose_engine()
