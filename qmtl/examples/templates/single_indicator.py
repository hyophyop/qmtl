from qmtl.sdk import Strategy, StreamInput, Runner
from qmtl.indicators import ema


class SingleIndicatorStrategy(Strategy):
    """Simple EMA example."""

    def setup(self):
        # Source price stream; real implementations would use a history provider
        price = StreamInput(interval="60s", period=20)
        # Apply an exponential moving average indicator
        ema_node = ema(price, window=10)
        # Register nodes with the strategy
        self.add_nodes([price, ema_node])


if __name__ == "__main__":
    # Run entirely offline using the default runner
    Runner.offline(SingleIndicatorStrategy)
