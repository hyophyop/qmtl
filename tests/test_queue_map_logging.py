import logging

from qmtl.runtime.sdk import Strategy, StreamInput, ProcessingNode, TagQueryNode
from qmtl.runtime.sdk.tag_manager_service import TagManagerService
from qmtl.services.dagmanager.kafka_admin import partition_key, compute_key


class _Strat(Strategy):
    def setup(self):
        self.src = StreamInput(interval="60s", period=2)
        self.proc = ProcessingNode(
            input=self.src, compute_fn=lambda v: v, name="proc", interval="60s", period=2
        )
        self.tq = TagQueryNode(["t"], interval="60s", period=2)
        self.add_nodes([self.src, self.proc, self.tq])


def test_apply_queue_map_logs_on_change(caplog):
    strat = _Strat()
    strat.setup()
    mapping = {
        partition_key(
            strat.proc.node_id,
            strat.proc.interval,
            0,
            compute_key=compute_key(strat.proc.node_id),
        ): "topic1",
        partition_key(
            strat.tq.node_id,
            strat.tq.interval,
            0,
            compute_key=compute_key(strat.tq.node_id),
        ): ["q1"],
    }

    service = TagManagerService(None)
    caplog.set_level(logging.DEBUG, logger="qmtl.runtime.sdk.tag_manager_service")
    service.apply_queue_map(strat, mapping)

    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "qmtl.runtime.sdk.tag_manager_service"
    ]
    assert any(strat.proc.node_id in m for m in msgs)
    assert any(strat.tq.node_id in m for m in msgs)

    caplog.clear()
    service.apply_queue_map(strat, mapping)
    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "qmtl.runtime.sdk.tag_manager_service"
    ]
    assert not msgs

