import asyncio
import asyncio
import pytest

import asyncio
import pytest

from qmtl.services.dagmanager.neo4j_metrics import GraphCountCollector, GraphCountScheduler
from qmtl.services.dagmanager import metrics


class FakeResult:
    def __init__(self, count: int) -> None:
        self.count = count

    def single(self) -> dict[str, int]:
        return {"c": self.count}


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, query: str) -> FakeResult:  # type: ignore[override]
        self.calls += 1
        return FakeResult(3 if "ComputeNode" in query else 7)

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass


class FakeDriver:
    def session(self) -> FakeSession:  # type: ignore[override]
        return FakeSession()


class EventCollector(GraphCountCollector):
    def __init__(self, driver, event):
        super().__init__(driver)
        self.event = event

    def record_counts(self) -> tuple[int, int]:  # type: ignore[override]
        res = super().record_counts()
        self.event.set()
        return res


def test_collector_sets_gauges() -> None:
    metrics.reset_metrics()
    collector = GraphCountCollector(FakeDriver())  # type: ignore[arg-type]
    compute, queues = collector.record_counts()
    assert compute == 3
    assert queues == 7
    assert metrics.compute_nodes_total._value.get() == 3  # type: ignore[attr-defined]
    assert metrics.queues_total._value.get() == 7  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_scheduler_runs() -> None:
    metrics.reset_metrics()
    event = asyncio.Event()
    collector = EventCollector(FakeDriver(), event)  # type: ignore[arg-type]
    sched = GraphCountScheduler(collector, interval=0.01)
    await sched.start()
    await asyncio.wait_for(event.wait(), timeout=1)
    await sched.stop()
    assert metrics.compute_nodes_total._value.get() == 3  # type: ignore[attr-defined]
    assert metrics.queues_total._value.get() == 7  # type: ignore[attr-defined]
