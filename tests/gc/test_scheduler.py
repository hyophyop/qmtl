import asyncio
import pytest

from qmtl.dagmanager.gc_scheduler import GCScheduler


class DummyGC:
    def __init__(self):
        self.calls = 0
        self.event = asyncio.Event()

    def collect(self):
        self.calls += 1
        self.event.set()
        return []


@pytest.mark.asyncio
async def test_gc_scheduler_runs_collect():
    gc = DummyGC()
    sched = GCScheduler(gc, interval=0.01)
    await sched.start()
    await asyncio.wait_for(gc.event.wait(), timeout=1)
    gc.event.clear()
    await asyncio.wait_for(gc.event.wait(), timeout=1)
    await sched.stop()
    assert gc.calls >= 2
