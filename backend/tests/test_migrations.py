import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def test_migrations_downgrade_and_upgrade_cleanly(alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


async def test_existing_organizations_get_the_default_template(
    alembic_config: Config, owner_engine: AsyncEngine
) -> None:
    from tests.helpers import new_organization

    org_id, _ = await new_organization("Before Sprint 2", "old@example.com")
    async with owner_engine.begin() as conn:
        await conn.execute(text("DELETE FROM project_templates"))

    await asyncio.to_thread(command.downgrade, alembic_config, "0003")
    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    async with owner_engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT t.name, count(i.*) FROM project_templates t "
                    "JOIN template_items i ON i.template_id = t.id "
                    "WHERE t.organization_id = :o GROUP BY t.name"
                ),
                {"o": org_id},
            )
        ).all()
    assert [(name, count) for name, count in rows] == [("Standard wedding (12 months)", 25)]
