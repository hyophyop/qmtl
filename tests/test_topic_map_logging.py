import logging

from qmtl.sdk import Runner, Strategy, StreamInput, ProcessingNode, TagQueryNode


class _Strat(Strategy):
    def setup(self):
        self.src = StreamInput(interval="60s", period=2)
        self.proc = ProcessingNode(
            input=self.src, compute_fn=lambda v: v, name="proc", interval="60s", period=2
        )
        self.tq = TagQueryNode(["t"], interval="60s", period=2)
        self.add_nodes([self.src, self.proc, self.tq])


def test_apply_topic_map_logs_on_change(caplog):
    strat = _Strat()
    strat.setup()
    topic_map = {strat.proc.node_id: "topic1", strat.tq.node_id: ["q1"]}

    caplog.set_level(logging.DEBUG, logger="qmtl.sdk.runner")
    Runner._apply_topic_map(strat, topic_map)

    msgs = [r.getMessage() for r in caplog.records if r.name == "qmtl.sdk.runner"]
    assert any(strat.proc.node_id in m for m in msgs)
    assert any(strat.tq.node_id in m for m in msgs)

    caplog.clear()
    Runner._apply_topic_map(strat, topic_map)
    msgs = [r.getMessage() for r in caplog.records if r.name == "qmtl.sdk.runner"]
    assert not msgs

