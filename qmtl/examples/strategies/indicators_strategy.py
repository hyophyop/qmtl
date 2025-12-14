"""Indicators strategy example - QMTL v2.0."""

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import StreamInput
from qmtl.runtime.indicators import ema


class EmaStrategy(Strategy):
    def setup(self):
        self.price = StreamInput(interval="60s", period=20)
        self.ema_node = ema(self.price, period=10)
        self.add_nodes([self.price, self.ema_node])


if __name__ == "__main__":
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(EmaStrategy)
    print(f"Strategy submitted: {result.status}")
