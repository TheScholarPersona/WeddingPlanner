"""Operator commands. Organizations are activated manually during the pilot.

    python -m app.cli create-organization --name "Atelier Lumière" --admin-email lena@example.com

Prints the invitation link for the first organization admin (the email is also queued).

    python -m app.cli send-digests --now

Sends today's daily overview emails right away instead of at the configured hour (each person
still gets at most one per day).
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


async def _send_digests() -> None:
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    from app.notifications.digest import digest_for_organization

    async with get_sessionmaker()() as db:
        orgs = (await db.execute(text("SELECT id, timezone FROM app_active_organizations()"))).all()
    total = 0
    for org_id, timezone in orgs:
        today = datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()
        total += await digest_for_organization(org_id, today)
    await dispose_engine()
    print(f"Queued {total} daily overview email(s).")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-organization", help="Create an organization")
    create.add_argument("--name", required=True)
    create.add_argument("--admin-email", required=True)
    digests = commands.add_parser("send-digests", help="Send today's daily overview emails")
    digests.add_argument("--now", action="store_true", required=True)
    args = parser.parse_args()

    get_settings()
    if args.command == "create-organization":
        asyncio.run(_create_organization(args.name, args.admin_email))
    elif args.command == "send-digests":
        asyncio.run(_send_digests())


if __name__ == "__main__":
    main()
