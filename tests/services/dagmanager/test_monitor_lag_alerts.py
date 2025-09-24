import pytest

from qmtl.services.dagmanager.monitor import Monitor, AckStatus
from qmtl.services.dagmanager.alerts import AlertManager


class LagMetrics:
    def __init__(self, lag: float, threshold: float, diff: float):
        self.lag = lag
        self.threshold = threshold
        self.diff = diff

    def neo4j_leader_is_null(self) -> bool:
        return False

    def kafka_zookeeper_disconnects(self) -> int:
        return 0

    def queue_lag_seconds(self, topic: str) -> tuple[float, float]:
        return self.lag, self.threshold

    def diff_duration_ms_p95(self) -> float:
        return self.diff


class NoopCluster:
    def elect_leader(self) -> None:
        pass


class NoopKafka:
    def retry(self) -> None:
        pass


class NoopStream:
    def ack_status(self) -> AckStatus:
        return AckStatus.OK

    def resume_from_last_offset(self) -> None:
        pass


class DummyPagerDuty:
    async def send(self, message: str, *, topic: str | None = None, node: str | None = None) -> None:
        pass


class CapturingSlack:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str | None, str | None]] = []

    async def send(self, message: str, *, topic: str | None = None, node: str | None = None) -> None:
        self.sent.append((message, topic, node))


@pytest.mark.asyncio
async def test_monitor_alerts_on_lag_and_diff_duration():
    metrics = LagMetrics(lag=15, threshold=10, diff=250)
    pd = DummyPagerDuty()
    slack = CapturingSlack()
    manager = AlertManager(pd, slack)
    monitor = Monitor(metrics, NoopCluster(), NoopKafka(), NoopStream(), manager, lag_topics=["prices"])

    await monitor.check_once()

    assert ("Queue lag high", "prices", None) in slack.sent
    assert ("Diff duration high", None, None) in slack.sent
