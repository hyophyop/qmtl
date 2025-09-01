import logging
import pytest

from qmtl.sdk import Strategy, StreamInput, ProcessingNode, TagQueryNode
from qmtl.sdk.tag_manager_service import TagManagerService
from qmtl.dagmanager.kafka_admin import partition_key


class _Strat(Strategy):
    def setup(self):
        self.src = StreamInput(interval="60s", period=2)
        self.proc = ProcessingNode(
            input=self.src, compute_fn=lambda v: v, name="proc", interval="60s", period=2
        )
        self.tq = TagQueryNode(["t"], interval="60s", period=2)
        self.add_nodes([self.src, self.proc, self.tq])


def test_init_attaches_manager():
    strat = _Strat()
    strat.setup()
    service = TagManagerService("http://gw")
    manager = service.init(strat)
    assert getattr(strat, "tag_query_manager") is manager


def test_apply_queue_map_updates_nodes(caplog):
    strat = _Strat()
    strat.setup()
    service = TagManagerService(None)
    mapping = {
        partition_key(strat.proc.node_id, strat.proc.interval, 0): "topic1",
        partition_key(strat.tq.node_id, strat.tq.interval, 0): ["q1"],
    }
    caplog.set_level(logging.DEBUG, logger="qmtl.sdk.tag_manager_service")
    service.apply_queue_map(strat, mapping)
    assert strat.proc.kafka_topic == "topic1"
    assert not strat.proc.execute
    assert strat.tq.upstreams == ["q1"]
    msgs = [
        r.getMessage()
        for r in caplog.records
        if r.name == "qmtl.sdk.tag_manager_service"
    ]
    assert any(strat.proc.node_id in m for m in msgs)
