from qmtl.runtime.sdk import ProcessingNode, Strategy, StreamInput


class SampleStrategy(Strategy):
    def setup(self):
        src = StreamInput(interval="1s", period=1)
        node = ProcessingNode(input=src, compute_fn=lambda df: df, name="out", interval="1s", period=1)
        self.add_nodes([src, node])
