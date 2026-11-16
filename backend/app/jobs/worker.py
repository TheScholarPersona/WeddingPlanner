"""ARQ worker: emails, virus scans, the daily digest and retention cleanup (ADR 007)."""

import logging
from typing import Any, ClassVar, cast

from arq import cron, func
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.documents.service import scan_document_job
from app.jobs.retention import purge
from app.notifications.digest import send_daily_digests
from app.notifications.mailer import send_email_job

logger = logging.getLogger(__name__)


async def heartbeat(_: dict[str, Any]) -> str:
    """Used to verify the worker runs."""
    logger.info("worker heartbeat")
    return "ok"


async def startup(_: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        heartbeat,
        func(cast(Any, send_email_job), name="send_email"),
        func(cast(Any, scan_document_job), name="scan_document", max_tries=3),
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(cast(Any, send_daily_digests), minute=5, run_at_startup=False),
        cron(cast(Any, purge), hour=3, minute=17, run_at_startup=False),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
