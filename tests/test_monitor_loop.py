import asyncio
import pytest

from qmtl.dagmanager.monitor import MonitorLoop


class DummyMonitor:
    def __init__(self):
        self.called = 0
        self.event = asyncio.Event()

    async def check_once(self) -> None:
        self.called += 1
        self.event.set()


@pytest.mark.asyncio
async def test_monitor_loop_runs_periodically():
    done = asyncio.Event()
    mon = DummyMonitor()
    mon.done = done  # type: ignore[attr-defined]
    loop = MonitorLoop(mon, interval=0.01)  # type: ignore[arg-type]
    await loop.start()
    await asyncio.wait_for(mon.event.wait(), timeout=1)
    mon.event.clear()
    await asyncio.wait_for(mon.event.wait(), timeout=1)
    await loop.stop()
    assert mon.called >= 2
