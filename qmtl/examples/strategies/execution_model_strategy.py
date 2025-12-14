"""Execution model strategy example - QMTL v2.0.

Demonstrates execution cost modeling with the simplified v2 API.
"""

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.transforms import alpha_history_node, TradeSignalGeneratorNode
from qmtl.runtime.transforms.alpha_performance import alpha_performance_node
from qmtl.runtime.sdk.execution_modeling import (
    ExecutionModel,
    OrderSide,
    OrderType,
    create_market_data_from_ohlcv,
)


class ExecutionModelStrategy(Strategy):
    """Strategy combining trade signals with execution cost modeling."""

    def setup(self) -> None:
        price_stream = StreamInput(interval="60s", period=5)

        def compute_return(view):
            data = [v for _, v in view[price_stream][60]]
            if len(data) < 2:
                return 0.0
            prev, last = data[-2]["close"], data[-1]["close"]
            return (last - prev) / prev

        returns = Node(
            input=price_stream,
            compute_fn=compute_return,
            name="returns",
        )

        history = alpha_history_node(returns, window=30)
        signal = TradeSignalGeneratorNode(
            history, long_threshold=0.0, short_threshold=0.0
        )

        model = ExecutionModel()

        def simulate_fill(view):
            sig_data = view[signal][signal.interval]
            price_data = view[price_stream][price_stream.interval]
            if not sig_data or not price_data:
                return None

            sig = sig_data[-1][1]
            if sig["action"] == "HOLD":
                return None

            bar_time, bar = price_data[-1]
            market = create_market_data_from_ohlcv(
                timestamp=bar_time,
                open_price=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
            )
            side = OrderSide.BUY if sig["action"] == "BUY" else OrderSide.SELL
            return model.simulate_execution(
                order_id=f"order_{bar_time}",
                symbol="ASSET",
                side=side,
                quantity=sig["size"],
                order_type=OrderType.MARKET,
                requested_price=bar["close"],
                market_data=market,
                timestamp=bar_time,
            )

        fill_node = Node(
            input=[signal, price_stream],
            compute_fn=simulate_fill,
            name="execution_fill",
            interval=price_stream.interval,
            period=1,
        )

        fills = alpha_history_node(fill_node, window=100, name="execution_fills")

        def compute_performance(view):
            hist_data = view[history][history.interval]
            fill_data = view[fills][fills.interval]
            if not hist_data:
                return None
            returns_series = hist_data[-1][1]
            exec_fills = [f for f in (fill_data[-1][1] if fill_data else []) if f]
            return alpha_performance_node(
                returns_series,
                execution_fills=exec_fills,
                use_realistic_costs=True,
            )

        performance = Node(
            input=[history, fills],
            compute_fn=compute_performance,
            name="performance",
            interval=history.interval,
            period=1,
        )

        self.add_nodes(
            [
                price_stream,
                returns,
                history,
                signal,
                fill_node,
                fills,
                performance,
            ]
        )


if __name__ == "__main__":
    # v2 API: submit to WorldService; stage/mode is governed by world policy
    result = Runner.submit(ExecutionModelStrategy)
    print(f"Strategy submitted: {result.status}")
