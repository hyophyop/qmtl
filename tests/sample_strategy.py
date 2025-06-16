from qmtl.sdk import Strategy, Node, StreamInput

class SampleStrategy(Strategy):
    def setup(self):
        src = StreamInput(interval=1, period=1)
        node = Node(input=src, compute_fn=lambda df: df, name="out", interval=1, period=1)
        self.add_nodes([src, node])
