"""Transforms strategy example - QMTL v2.0."""

from qmtl.runtime.sdk import Runner, Strategy, Mode
from qmtl.runtime.sdk.node import StreamInput
from qmtl.runtime.transforms import rate_of_change


class RocStrategy(Strategy):
    def setup(self):
        self.price = StreamInput(interval="60s", period=5)
        self.roc_node = rate_of_change(self.price, period=3)
        self.add_nodes([self.price, self.roc_node])


if __name__ == "__main__":
    # v2 API: backtest mode for local validation
    result = Runner.submit(RocStrategy, mode=Mode.BACKTEST)
    print(f"Strategy submitted: {result.status}")
