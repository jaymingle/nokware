"""Run a blocking job on a fixed interval inside the API process, so deadlines hold without cron.

One run at a time: the next run waits for the previous one to finish plus the interval.
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


async def run_every(interval_seconds: float, job: Callable[[], object], name: str) -> None:
    while True:
        try:
            await asyncio.to_thread(job)
        except Exception:
            logger.exception("%s failed; retrying in %ss", name, interval_seconds)
        await asyncio.sleep(interval_seconds)


def start(interval_seconds: float, job: Callable[[], object], name: str) -> asyncio.Task[None] | None:
    if interval_seconds <= 0:
        logger.info("%s is disabled", name)
        return None
    logger.info("%s runs every %ss", name, interval_seconds)
    return asyncio.create_task(run_every(interval_seconds, job, name), name=name)


async def stop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
