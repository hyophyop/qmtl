"""Strategy demonstrating lifecycle callbacks for state management."""

from qmtl.sdk import Strategy, StreamInput, ProcessingNode, buy_signal


class CallbackStateStrategy(Strategy):
    """Simple strategy using callbacks to track position state."""

    def __init__(self):
        super().__init__(default_interval="1s", default_period=1)
        self.in_position = False

    def setup(self):
        price = StreamInput()
        # Echo node just forwards the latest price
        echo = ProcessingNode(input=price, compute_fn=lambda v: v, name="echo")
        self.add_nodes([price, echo])

    def on_start(self) -> None:
        self.in_position = False

    def on_signal(self, signal) -> None:
        # Update internal state based on generated signals
        action = signal.get("action")
        if action == "BUY":
            self.in_position = True
        elif action == "SELL":
            self.in_position = False

    def on_fill(self, order, fill) -> None:
        # Sync state when an order fill occurs
        self.in_position = order.get("action") == "BUY"

    def on_finish(self) -> None:
        self.in_position = False


__all__ = ["CallbackStateStrategy", "buy_signal"]
