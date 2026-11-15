"""Row-level security foundation: the guarantees every tenant table will rely on."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.rls import enable_tenant_rls
from app.db.tenant import set_tenant_context

ORG_A = uuid.UUID("00000000-0000-7000-8000-00000000000a")
ORG_B = uuid.UUID("00000000-0000-7000-8000-00000000000b")
USER = uuid.UUID("00000000-0000-7000-8000-000000000001")


@pytest.fixture
async def demo_table(owner_engine: AsyncEngine) -> AsyncIterator[str]:
    """A throwaway tenant table, created the way real migrations will create them."""
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE rls_demo (id serial PRIMARY KEY, "
                "organization_id uuid NOT NULL, label text NOT NULL)"
            )
        )
        for statement in enable_tenant_rls("rls_demo"):
            await conn.execute(text(statement))
    yield "rls_demo"
    async with owner_engine.begin() as conn:
        await conn.execute(text("DROP TABLE rls_demo"))


async def _insert(session: AsyncSession, org: uuid.UUID, label: str) -> None:
    await session.execute(
        text("INSERT INTO rls_demo (organization_id, label) VALUES (:org, :label)"),
        {"org": org, "label": label},
    )


async def test_app_role_cannot_bypass_rls(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = current_user")
            )
        ).one()

    assert row.rolbypassrls is False
    assert row.rolsuper is False


async def test_rows_are_visible_only_to_their_organization(
    app_engine: AsyncEngine, demo_table: str
) -> None:
    sessions = async_sessionmaker(app_engine)
    for org, label in ((ORG_A, "a-row"), (ORG_B, "b-row")):
        async with sessions() as session, session.begin():
            await set_tenant_context(session, organization_id=org, user_id=USER, role="org_admin")
            await _insert(session, org, label)

    async with sessions() as session, session.begin():
        await set_tenant_context(session, organization_id=ORG_A, user_id=USER, role="member")
        labels = (await session.execute(text("SELECT label FROM rls_demo"))).scalars().all()

    assert labels == ["a-row"]


async def test_no_tenant_context_sees_nothing(app_engine: AsyncEngine, demo_table: str) -> None:
    sessions = async_sessionmaker(app_engine)
    async with sessions() as session, session.begin():
        await set_tenant_context(session, organization_id=ORG_A, user_id=USER, role="org_admin")
        await _insert(session, ORG_A, "a-row")

    async with sessions() as session, session.begin():
        count = (await session.execute(text("SELECT count(*) FROM rls_demo"))).scalar_one()

    assert count == 0


async def test_cannot_write_rows_for_another_organization(
    app_engine: AsyncEngine, demo_table: str
) -> None:
    sessions = async_sessionmaker(app_engine)
    with pytest.raises(DBAPIError, match="row-level security"):
        async with sessions() as session, session.begin():
            await set_tenant_context(session, organization_id=ORG_A, user_id=USER, role="org_admin")
            await _insert(session, ORG_B, "smuggled")


async def test_tenant_context_does_not_outlive_the_transaction(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.org_id', :v, true)"), {"v": str(ORG_A)})
        after = (await conn.execute(text("SELECT app_current_org_id()"))).scalar_one()

    assert after is None


def test_rls_builder_rejects_unsafe_identifiers() -> None:
    with pytest.raises(ValueError):
        enable_tenant_rls("tasks; DROP TABLE users")


async def test_every_tenant_table_has_row_level_security(owner_engine: AsyncEngine) -> None:
    """A new table with organization_id must not be created without a policy."""
    async with owner_engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, "
                    "EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) AS has_policy "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'organization_id' "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'rls_demo'"
                )
            )
        ).all()
    assert len(rows) >= 25
    assert [r.relname for r in rows if not (r.relrowsecurity and r.has_policy)] == []
