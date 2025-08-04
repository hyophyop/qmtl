import pytest
from qmtl.dagmanager.monitor import Monitor, MetricsBackend, Neo4jCluster, KafkaSession
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
    pd = FakePagerDuty()
    slack = FakeSlack()
    manager = AlertManager(pd, slack)
    monitor = Monitor(metrics, cluster, kafka, manager)

    await monitor.check_once()

    assert cluster.elected == 1
    assert kafka.retried == 1
    assert pd.sent == ["Neo4j leader down"]
    assert slack.sent == ["Kafka session lost"]
