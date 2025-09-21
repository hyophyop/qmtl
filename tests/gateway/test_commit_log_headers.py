import json
import pytest

from qmtl.dagmanager.kafka_admin import compute_key
from qmtl.gateway.commit_log import CommitLogWriter


class ProducerWithHeaders:
    def __init__(self) -> None:
        self.records: list[tuple[str, bytes, bytes, list[tuple[str, bytes]] | None]] = []
        self.started = False
        self.committed = 0

    async def begin_transaction(self) -> None:
        return None

    async def send_and_wait(self, topic, *, key=None, value=None, headers=None):
        self.records.append((topic, key, value, headers))

    async def commit_transaction(self) -> None:
        self.committed += 1


@pytest.mark.asyncio
async def test_commit_log_writer_attaches_runtime_fingerprint_header():
    p = ProducerWithHeaders()
    w = CommitLogWriter(p, "t")
    await w.publish_bucket(100, 60, [("n1", "h1", {"x": 1}, compute_key("n1"))])
    assert p.committed == 1
    assert p.records and isinstance(p.records[-1][3], list)
    headers = dict((k, v) for k, v in p.records[-1][3] or [])
    assert b"rfp" in headers or "rfp" in headers

