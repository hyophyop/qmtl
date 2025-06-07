from datetime import datetime, timedelta

from qmtl.dagmanager.gc import GarbageCollector, QueueInfo


class FakeStore:
    def __init__(self, queues=None):
        self.queues = queues or []
        self.dropped = []

    def list_orphan_queues(self):
        return list(self.queues)

    def drop_queue(self, name: str) -> None:
        self.dropped.append(name)


class FakeMetrics:
    def __init__(self, value: float):
        self.value = value

    def messages_in_per_sec(self) -> float:
        return self.value


class FakeArchive:
    def __init__(self):
        self.archived = []

    def archive(self, queue: str) -> None:
        self.archived.append(queue)


def test_gc_policy_drop_and_archive():
    now = datetime.utcnow()
    queues = [
        QueueInfo("raw_q", "raw", now - timedelta(days=10)),
        QueueInfo("sentinel_q", "sentinel", now - timedelta(days=220)),
    ]
    store = FakeStore(queues)
    metrics = FakeMetrics(10)
    archive = FakeArchive()
    gc = GarbageCollector(store, metrics, archive=archive, batch_size=10)

    processed = gc.collect(now)

    assert processed == ["raw_q", "sentinel_q"]
    assert store.dropped == ["raw_q", "sentinel_q"]
    assert archive.archived == ["sentinel_q"]


def test_gc_batch_halved_on_high_load():
    now = datetime.utcnow()
    queues = [
        QueueInfo(f"q{i}", "raw", now - timedelta(days=10)) for i in range(4)
    ]
    store = FakeStore(queues)
    metrics = FakeMetrics(85)
    gc = GarbageCollector(store, metrics, batch_size=4)

    gc.collect(now)

    assert len(store.dropped) == 2


def test_gc_respects_grace_period():
    now = datetime.utcnow()
    # Queue age is exactly TTL but within grace period
    queues = [QueueInfo("q", "raw", now - timedelta(days=7))]
    store = FakeStore(queues)
    metrics = FakeMetrics(0)
    gc = GarbageCollector(store, metrics, batch_size=1)

    processed = gc.collect(now)

    assert processed == []
    assert store.dropped == []


def test_gc_archives_with_client():
    now = datetime.utcnow()
    queues = [QueueInfo("s", "sentinel", now - timedelta(days=400))]
    store = FakeStore(queues)
    metrics = FakeMetrics(0)
    archive = FakeArchive()
    gc = GarbageCollector(store, metrics, archive=archive, batch_size=1)

    processed = gc.collect(now)

    assert processed == ["s"]
    assert store.dropped == ["s"]
    assert archive.archived == ["s"]
