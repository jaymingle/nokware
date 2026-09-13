"""The in-process runner behind the deadline job."""

import asyncio

from app.services import scheduler


def test_runs_repeatedly_and_survives_a_failing_run() -> None:
    calls: list[int] = []

    def job() -> None:
        calls.append(len(calls))
        if len(calls) == 2:
            raise RuntimeError("Appwrite unreachable")

    async def main() -> None:
        task = scheduler.start(0.01, job, "test job")
        await asyncio.sleep(0.2)
        await scheduler.stop(task)

    asyncio.run(main())
    assert len(calls) >= 3  # ran again after the failure


def test_an_interval_of_zero_disables_it() -> None:
    assert scheduler.start(0, lambda: None, "off") is None
