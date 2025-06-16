from qmtl.sdk import Strategy, Runner
from qmtl.generators import GarchInput
from qmtl.indicators import ema
from qmtl.transforms import rate_of_change


class CombinedExtensionsStrategy(Strategy):
    def setup(self):
        self.source = GarchInput(interval=60, period=30, seed=42)
        self.ema_node = ema(self.source, window=5)
        self.roc_node = rate_of_change(self.ema_node, period=5)
        self.add_nodes([self.source, self.ema_node, self.roc_node])

if __name__ == "__main__":
    Runner.offline(CombinedExtensionsStrategy)
