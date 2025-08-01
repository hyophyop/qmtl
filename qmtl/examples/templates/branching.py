from qmtl.sdk import Strategy, StreamInput, Node, Runner
import pandas as pd


class BranchingStrategy(Strategy):
    """Demonstrate branching computations from one source."""

    def setup(self):
        price = StreamInput(interval="60s", period=30)

        def calc_momentum(view):
            df = pd.DataFrame([v for _, v in view[price][60]])
            return pd.DataFrame({"momentum": df["close"].pct_change()})

        def calc_volatility(view):
            df = pd.DataFrame([v for _, v in view[price][60]])
            vol = df["close"].pct_change().rolling(10).std()
            return pd.DataFrame({"volatility": vol})

        momentum = Node(input=price, compute_fn=calc_momentum, name="momentum")
        volatility = Node(input=price, compute_fn=calc_volatility, name="volatility")
        self.add_nodes([price, momentum, volatility])


if __name__ == "__main__":
    Runner.offline(BranchingStrategy)
