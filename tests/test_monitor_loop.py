import pytest

from qmtl.dagmanager.monitor import MonitorLoop


class DummyMonitor:
    def __init__(self):
        self.called = 0

    async def check_once(self) -> None:
        self.called += 1


@pytest.mark.asyncio
async def test_monitor_loop_runs_periodically():
    mon = DummyMonitor()
    loop = MonitorLoop(mon, interval=0.01)  # type: ignore[arg-type]
    await loop.start()
    await loop.trigger()
    await loop.trigger()
    await loop.stop()
    assert mon.called == 2
