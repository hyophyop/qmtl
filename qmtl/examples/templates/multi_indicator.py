from qmtl.sdk import Strategy, StreamInput, Runner
from qmtl.indicators import ema, rsi


class MultiIndicatorStrategy(Strategy):
    """Combine several indicators from one input."""

    def setup(self):
        price = StreamInput(interval="60s", period=50)
        fast_ema = ema(price, window=5)
        slow_ema = ema(price, window=20)
        rsi_node = rsi(price, window=14)
        self.add_nodes([price, fast_ema, slow_ema, rsi_node])


if __name__ == "__main__":
    Runner.offline(MultiIndicatorStrategy)
