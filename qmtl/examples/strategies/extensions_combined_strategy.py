"""Combined extensions strategy example - QMTL v2.0."""

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.generators import GarchInput
from qmtl.runtime.indicators import ema
from qmtl.runtime.transforms import rate_of_change


class CombinedExtensionsStrategy(Strategy):
    def setup(self):
        self.source = GarchInput(interval="60s", period=30, seed=42)
        self.ema_node = ema(self.source, period=5)
        self.roc_node = rate_of_change(self.ema_node, period=5)
        self.add_nodes([self.source, self.ema_node, self.roc_node])


if __name__ == "__main__":
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(CombinedExtensionsStrategy)
    print(f"Strategy submitted: {result.status}")
