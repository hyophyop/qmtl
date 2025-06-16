from qmtl.sdk import Strategy, StreamInput, Runner
from qmtl.transforms import rate_of_change


class RocStrategy(Strategy):
    def setup(self):
        self.price = StreamInput(interval=60, period=5)
        self.roc_node = rate_of_change(self.price, period=3)
        self.add_nodes([self.price, self.roc_node])

    def define_execution(self):
        self.set_target(self.roc_node.name)


if __name__ == "__main__":
    Runner.offline(RocStrategy)
