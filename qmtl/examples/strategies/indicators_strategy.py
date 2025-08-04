from qmtl.sdk import Strategy, StreamInput, Runner
from qmtl.indicators import ema


class EmaStrategy(Strategy):
    def setup(self):
        self.price = StreamInput(interval="60s", period=20)
        self.ema_node = ema(self.price, period=10)
        self.add_nodes([self.price, self.ema_node])

if __name__ == "__main__":
    Runner.offline(EmaStrategy)
