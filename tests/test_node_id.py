from qmtl.sdk import Node, StreamInput, Strategy

def test_node_id_generation():
    node = Node(compute_fn=lambda x: x, name="n", interval=1, period=1)
    node_id = node.node_id
    assert len(node_id) == 64
    assert node_id == node.node_id  # deterministic


class _S(Strategy):
    def setup(self):
        src = StreamInput(interval=1, period=1)
        node = Node(input=src, compute_fn=lambda x: x, name="out", interval=1, period=1)
        self.add_nodes([src, node])

    def define_execution(self):
        self.set_target("out")


def test_strategy_serialize():
    s = _S()
    s.setup()
    s.define_execution()
    dag = s.serialize()
    assert "nodes" in dag
    ids = [n["node_id"] for n in dag["nodes"]]
    assert all(len(i) == 64 for i in ids)
