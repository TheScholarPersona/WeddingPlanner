"""Operator commands. Organizations are activated manually during the pilot.

    python -m app.cli create-organization --name "Atelier Lumière" --admin-email lena@example.com

Prints the invitation link for the first organization admin (the email is also queued).
"""

import argparse
import asyncio

from app.core.config import get_settings
from app.db.session import dispose_engine, get_sessionmaker
from app.organizations.service import create_organization


async def _create_organization(name: str, admin_email: str) -> None:
    async with get_sessionmaker()() as db:
        org, link = await create_organization(db, name=name, admin_email=admin_email)
        await db.commit()
    await dispose_engine()
    print(f"Created organization '{org.name}' ({org.id}).")
    print(f"Invitation for the first admin ({admin_email}):\n{link}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-organization", help="Create an organization")
    create.add_argument("--name", required=True)
    create.add_argument("--admin-email", required=True)
    args = parser.parse_args()

    get_settings()
    if args.command == "create-organization":
        asyncio.run(_create_organization(args.name, args.admin_email))


if __name__ == "__main__":
    main()
