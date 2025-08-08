from qmtl.sdk import SourceNode, ProcessingNode, StreamInput, Strategy

def test_node_id_generation():
    node = SourceNode(compute_fn=lambda x: x, name="n", interval="1s", period=1)
    node_id = node.node_id
    assert len(node_id) == 64
    assert node_id == node.node_id  # deterministic


class _S(Strategy):
    def setup(self):
        src = StreamInput(interval="1s", period=1)
        node = ProcessingNode(input=src, compute_fn=lambda x: x, name="out", interval="1s", period=1)
        self.add_nodes([src, node])


def test_strategy_serialize():
    s = _S()
    s.setup()
    dag = s.serialize()
    assert "nodes" in dag
    ids = [n["node_id"] for n in dag["nodes"]]
    assert all(len(i) == 64 for i in ids)
