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


_FOOTER = (
    "\n—\nYou receive this email because of your notification settings. "
    "Change them here: {settings}\n"
)


def _with_footer(text: str, settings_link: str) -> str:
    return text + _FOOTER.format(settings=settings_link)


def task_assigned_email(
    to: str, actor: str, task_title: str, wedding_title: str, link: str, settings_link: str
) -> Email:
    return Email(
        to=to,
        subject=f"New task for you: {task_title}",
        text=_with_footer(
            f"Hello,\n\n{actor} assigned a task to you in “{wedding_title}”:\n\n"
            f"  {task_title}\n\nOpen it here:\n{link}\n",
            settings_link,
        ),
    )


def comment_email(
    to: str, actor: str, target_title: str, wedding_title: str, link: str, settings_link: str
) -> Email:
    # The comment itself is not copied into the email; it stays in the platform.
    return Email(
        to=to,
        subject=f"New comment on “{target_title}”",
        text=_with_footer(
            f"Hello,\n\n{actor} commented on “{target_title}” in “{wedding_title}”.\n\n"
            f"Read and reply here:\n{link}\n",
            settings_link,
        ),
    )


def document_email(
    to: str, actor: str, document_title: str, wedding_title: str, link: str, settings_link: str
) -> Email:
    return Email(
        to=to,
        subject=f"New document: {document_title}",
        text=_with_footer(
            f"Hello,\n\n{actor} shared a document in “{wedding_title}”:\n\n"
            f"  {document_title}\n\nOpen it here:\n{link}\n",
            settings_link,
        ),
    )


def digest_email(to: str, organization_name: str, lines: list[str], settings_link: str) -> Email:
    body = "\n".join(lines)
    return Email(
        to=to,
        subject=f"Your day ahead with {organization_name}",
        text=_with_footer(
            f"Good morning,\n\nhere is what is coming up:\n\n{body}\n", settings_link
        ),
    )
