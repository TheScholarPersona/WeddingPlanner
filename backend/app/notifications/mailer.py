"""Outgoing email. Requests only queue emails; the ARQ worker sends them (ADR 007).

All email copy is English, like the UI.
"""

from dataclasses import asdict, dataclass
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str


# Collected emails when EMAIL_BACKEND=memory (tests, local scripts without a worker).
OUTBOX: list[Email] = []

_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(str(get_settings().redis_url)))
    return _pool


async def queue_email(email: Email) -> None:
    if get_settings().email_backend == "memory":
        OUTBOX.append(email)
        return
    pool = await _get_pool()
    await pool.enqueue_job("send_email", asdict(email))


async def send_email_now(email: Email) -> None:
    """Called by the worker job."""
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    await aiosmtplib.send(message, hostname=settings.smtp_host, port=settings.smtp_port)


async def send_email_job(_: dict[str, Any], payload: dict[str, str]) -> None:
    await send_email_now(Email(**payload))


# --- Templates ----------------------------------------------------------------------------


def invitation_email(to: str, organization_name: str, inviter_name: str | None, link: str) -> Email:
    who = inviter_name or organization_name
    return Email(
        to=to,
        subject=f"You're invited to join {organization_name}",
        text=(
            f"Hello,\n\n{who} invited you to join {organization_name} on the Wedding Planning "
            f"Platform.\n\nAccept the invitation here:\n{link}\n\n"
            "The link is valid for 7 days and can be used once. If you did not expect this "
            "email, you can ignore it.\n"
        ),
    )


def password_reset_email(to: str, link: str) -> Email:
    return Email(
        to=to,
        subject="Reset your password",
        text=(
            "Hello,\n\nWe received a request to reset your password. Choose a new password "
            f"here:\n{link}\n\nThe link is valid for 60 minutes. If you did not request this, "
            "you can ignore this email; your password stays unchanged.\n"
        ),
    )


def couple_invitation_email(
    to: str, organization_name: str, wedding_title: str, link: str
) -> Email:
    return Email(
        to=to,
        subject=f"Your wedding portal with {organization_name}",
        text=(
            f"Hello,\n\n{organization_name} invited you to the wedding portal for "
            f"“{wedding_title}”. There you can follow your planning, tick off your tasks and "
            f"keep an eye on your budget.\n\nCreate your access here:\n{link}\n\n"
            "The link is valid for 7 days and can be used once. If you did not expect this "
            "email, you can ignore it.\n"
        ),
    )
