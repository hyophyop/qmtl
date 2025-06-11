from qmtl.sdk import Strategy, Node, StreamInput, Runner
import pandas as pd

class GeneralStrategy(Strategy):
    def setup(self):
        price_stream = StreamInput(interval=60, period=30)

        def generate_signal(view):
            price = pd.DataFrame([v for _, v in view[price_stream][60]])
            momentum = price["close"].pct_change().rolling(5).mean()
            signal = (momentum > 0).astype(int)
            return pd.DataFrame({"signal": signal})

        signal_node = Node(
            input=price_stream,
            compute_fn=generate_signal,
            name="momentum_signal",
        )
        self.add_nodes([price_stream, signal_node])

    def define_execution(self):
        self.set_target("momentum_signal")


if __name__ == "__main__":
    Runner.backtest(
        GeneralStrategy,
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-02-01T00:00:00Z",
        on_missing="skip",
    )
