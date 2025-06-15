from qmtl.sdk import Strategy, StreamInput, Runner
from qmtl.indicators import ema


class EmaStrategy(Strategy):
    def setup(self):
        self.price = StreamInput(interval=60, period=20)
        self.ema_node = ema(self.price, window=10)
        self.add_nodes([self.price, self.ema_node])

    def define_execution(self):
        self.set_target(self.ema_node.name)


if __name__ == "__main__":
    Runner.offline(EmaStrategy)
