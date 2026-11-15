"""Hand work to the background worker (ADR 007).

Request handlers collect jobs in `Jobs`; once the handler succeeded, the transaction is
committed and only then are the jobs enqueued, so the worker always finds the rows a job
refers to. With JOB_BACKEND=inline (tests) the job function runs in-process at that point.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import Depends

from app.authz.deps import DbSession
from app.core.config import get_settings

logger = logging.getLogger(__name__)
JobFunction = Callable[..., Awaitable[Any]]
_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(str(get_settings().redis_url)))
    return _pool


async def run_or_enqueue(name: str, function: JobFunction, *args: Any) -> None:
    if get_settings().job_backend == "inline":
        await function({}, *args)
        return
    await (await _get_pool()).enqueue_job(name, *args)


@dataclass
class PendingJobs:
    items: list[tuple[str, JobFunction, tuple[Any, ...]]] = field(default_factory=list)

    def add(self, name: str, function: JobFunction, *args: Any) -> None:
        self.items.append((name, function, args))


async def _pending_jobs(db: DbSession) -> AsyncIterator[PendingJobs]:
    jobs = PendingJobs()
    yield jobs  # an exception in the handler skips the rest: nothing is enqueued
    if not jobs.items:
        return
    await db.commit()
    for name, function, args in jobs.items:
        try:
            await run_or_enqueue(name, function, *args)
        except Exception:
            # The row stays in its pending state and is visible as such in the app.
            logger.exception("could not enqueue job", extra={"job": name})


Jobs = Annotated[PendingJobs, Depends(_pending_jobs)]
