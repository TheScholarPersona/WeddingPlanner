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


async def _grant_platform_admin(email: str) -> None:
    from sqlalchemy import update

    from app.auth.models import User

    async with get_sessionmaker()() as db:
        result = await db.execute(
            update(User).where(User.email == email.lower()).values(is_platform_admin=True)
        )
        await db.commit()
    await dispose_engine()
    if not result.rowcount:  # type: ignore[attr-defined]
        raise SystemExit(f"No account with the email {email}.")
    print(f"{email} is now a platform admin. They must turn on two-factor authentication.")


async def _seed_demo(name: str) -> None:
    from app.demo import seed_demo

    result = await seed_demo(name)
    await dispose_engine()
    print(f"Demo organization '{result['organization']}' is ready. Sign in at /login with:")
    for role in ("admin", "planner", "couple"):
        print(f"  {role:8} {result[role + '_email']}  /  {result[role + '_password']}")
    print("Only invented data; email addresses use example.com and receive nothing.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-organization", help="Create an organization")
    create.add_argument("--name", required=True)
    create.add_argument("--admin-email", required=True)
    digests = commands.add_parser("send-digests", help="Send today's daily overview emails")
    digests.add_argument("--now", action="store_true", required=True)
    grant = commands.add_parser("grant-platform-admin", help="Make an account a platform admin")
    grant.add_argument("--email", required=True)
    demo = commands.add_parser("seed-demo", help="Create a demo organization with invented data")
    demo.add_argument("--name", default="Atelier Lumière (Demo)")
    args = parser.parse_args()

    get_settings()
    if args.command == "create-organization":
        asyncio.run(_create_organization(args.name, args.admin_email))
    elif args.command == "seed-demo":
        asyncio.run(_seed_demo(args.name))
    elif args.command == "grant-platform-admin":
        asyncio.run(_grant_platform_admin(args.email))
    elif args.command == "send-digests":
        asyncio.run(_send_digests())


if __name__ == "__main__":
    main()
