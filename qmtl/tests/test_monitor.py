import asyncio
import pytest
from qmtl.dagmanager.monitor import (
    Monitor,
    MetricsBackend,
    Neo4jCluster,
    KafkaSession,
    DiffStream,
    AckStatus,
)
from qmtl.dagmanager.alerts import AlertManager


class FakeMetrics:
    def __init__(self, leader=False, disconnects=0):
        self.leader = leader
        self.disconnects = disconnects

    def neo4j_leader_is_null(self) -> bool:
        return self.leader

    def kafka_zookeeper_disconnects(self) -> int:
        return self.disconnects


class FakeCluster:
    def __init__(self):
        self.elected = 0

    def elect_leader(self) -> None:
        self.elected += 1


class FakeKafka:
    def __init__(self):
        self.retried = 0

    def retry(self) -> None:
        self.retried += 1


class FakeStream:
    def __init__(self, status=AckStatus.OK):
        self.resumed = 0
        self.status = status

    def ack_status(self) -> AckStatus:
        return self.status

    def resume_from_last_offset(self) -> None:
        self.resumed += 1


class FakePagerDuty:
    def __init__(self):
        self.sent = []

    async def send(self, msg: str) -> None:
        self.sent.append(msg)


class FakeSlack:
    def __init__(self):
        self.sent = []

    async def send(self, msg: str) -> None:
        self.sent.append(msg)


@pytest.mark.asyncio
async def test_monitor_triggers_recovery_and_alerts():
    metrics = FakeMetrics(leader=True, disconnects=1)
    cluster = FakeCluster()
    kafka = FakeKafka()
    stream = FakeStream(status=AckStatus.TIMEOUT)
    pd = FakePagerDuty()
    slack = FakeSlack()
    manager = AlertManager(pd, slack)
    monitor = Monitor(metrics, cluster, kafka, stream, manager)

    await monitor.check_once()

    assert cluster.elected == 1
    assert kafka.retried == 1
    assert stream.resumed == 1
    assert pd.sent == ["Neo4j leader down"]
    assert "Kafka session lost" in slack.sent
    assert "Diff stream stalled" in slack.sent


@pytest.mark.asyncio
async def test_monitor_gathers_alerts_concurrently():
    metrics = FakeMetrics(leader=True, disconnects=1)
    cluster = FakeCluster()
    kafka = FakeKafka()
    stream = FakeStream(status=AckStatus.TIMEOUT)

    class SlowPagerDuty(FakePagerDuty):
        async def send(self, msg: str) -> None:  # type: ignore[override]
            assert cluster.elected == 1
            await asyncio.sleep(0.05)
            await super().send(msg)

    class SlowSlack(FakeSlack):
        async def send(self, msg: str) -> None:  # type: ignore[override]
            if msg == "Kafka session lost":
                assert kafka.retried == 1
            elif msg == "Diff stream stalled":
                assert stream.resumed == 1
            await asyncio.sleep(0.05)
            await super().send(msg)

    pd = SlowPagerDuty()
    slack = SlowSlack()
    manager = AlertManager(pd, slack)
    monitor = Monitor(metrics, cluster, kafka, stream, manager)

    start = asyncio.get_running_loop().time()
    await monitor.check_once()
    elapsed = asyncio.get_running_loop().time() - start

    assert elapsed < 0.1
    assert pd.sent == ["Neo4j leader down"]
    assert slack.sent.count("Kafka session lost") == 1
    assert slack.sent.count("Diff stream stalled") == 1
