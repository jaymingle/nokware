"""Run a blocking job on a fixed interval inside the API process.

Used for the deadline job, so documents publish when their clock runs out
without cron or an external scheduler. The job runs in a worker thread (it
blocks on Appwrite, MinIO and Gemini), one run at a time: the next run waits
for the previous one to finish plus the interval. A failed run is logged and
the loop carries on.
"""

import asyncio
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


async def run_every(interval_seconds: float, job: Callable[[], object], name: str) -> None:
    """Run job now and then every interval_seconds, until the task is cancelled."""
    while True:
        try:
            await asyncio.to_thread(job)
        except Exception:
            logger.exception("%s failed; retrying in %ss", name, interval_seconds)
        await asyncio.sleep(interval_seconds)


def start(interval_seconds: float, job: Callable[[], object], name: str) -> asyncio.Task[None] | None:
    """Start the loop on the running event loop; an interval of 0 or less disables it."""
    if interval_seconds <= 0:
        logger.info("%s is disabled", name)
        return None
    logger.info("%s runs every %ss", name, interval_seconds)
    return asyncio.create_task(run_every(interval_seconds, job, name), name=name)


async def stop(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
