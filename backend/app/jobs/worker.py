"""ARQ worker: emails, virus scans, reminders and cleanup jobs run here (ADR 007)."""

import logging
from typing import Any, ClassVar, cast

from arq import func
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.notifications.mailer import send_email_job

logger = logging.getLogger(__name__)


async def heartbeat(_: dict[str, Any]) -> str:
    """Placeholder job used to verify the worker runs; real jobs arrive in later sprints."""
    logger.info("worker heartbeat")
    return "ok"


async def startup(_: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [heartbeat, func(cast(Any, send_email_job), name="send_email")]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
