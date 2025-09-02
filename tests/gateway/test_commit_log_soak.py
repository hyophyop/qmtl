import json
import pytest

from qmtl.gateway import metrics
from qmtl.gateway.commit_log import CommitLogWriter
from qmtl.gateway.commit_log_consumer import CommitLogConsumer


class P:
    def __init__(self) -> None:
        self.buf = []

    async def begin_transaction(self):
        return None

    async def send_and_wait(self, topic, *, key=None, value=None, headers=None):
        self.buf.append((topic, key, value, headers))

    async def commit_transaction(self):
        return None


class _M:
    def __init__(self, value: bytes) -> None:
        self.value = value


class C:
    def __init__(self, batches):
        self._batches = list(batches)
        self.commit_calls = 0

    async def start(self):
        return None

    async def stop(self):
        return None

    async def getmany(self, timeout_ms=None):
        if self._batches:
            return {None: self._batches.pop(0)}
        return {}

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_commit_log_exactly_once_soak():
    metrics.reset_metrics()
    p = P()
    w = CommitLogWriter(p, "t")
    n = 100
    # produce duplicates for the same (node, bucket, input_hash)
    await w.publish_bucket(100, 60, [("n1", "ih", {"v": i % 3}) for i in range(n)])

    batch = [_M(v) for (_, _, v, _) in p.buf]
    # consumer
    c = C([batch])
    clc = CommitLogConsumer(c, topic="t", group_id="g")

    out = []

    async def handler(records):
        out.extend(records)

    await clc.start()
    await clc.consume(handler)
    await clc.stop()

    # Only the first record survives dedup
    assert len(out) == 1
    assert metrics.commit_duplicate_total._value.get() == n - 1
    assert c.commit_calls == 1
