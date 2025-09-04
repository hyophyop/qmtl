import asyncio
import pytest

from qmtl.dagmanager.gc_scheduler import GCScheduler


class DummyGC:
    def __init__(self, done: asyncio.Event):
        self.calls = 0
        self.done = done

    def collect(self):
        self.calls += 1
        if self.calls >= 2:
            self.done.set()
        return []


@pytest.mark.asyncio
async def test_gc_scheduler_runs_collect():
    done = asyncio.Event()
    gc = DummyGC(done)
    sched = GCScheduler(gc, interval=0.01)
    await sched.start()
    await asyncio.wait_for(done.wait(), timeout=1)
    await sched.stop()
    assert gc.calls >= 2
