"""Example strategy demonstrating order publication pipeline.

This example explicitly shows a fan-in (multi-upstream) node: a node that reads
from two upstreams at once. We combine the alpha history with the raw price
stream to gate long signals when the short-term price trend is down.
"""

from qmtl.sdk import Strategy, StreamInput, Node, Runner, TradeExecutionService
from qmtl.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)
from qmtl.pipeline.execution_nodes import RouterNode
from qmtl.pipeline.micro_batch import MicroBatchNode


class OrderPipelineStrategy(Strategy):
    """Chain alpha history -> trade signal -> order publisher."""

    def setup(self) -> None:
        price = StreamInput(interval="60s", period=2)

        def compute_alpha(view):
            data = view[price][price.interval]
            if len(data) < 2:
                return 0.0
            prev, last = data[-2][1]["close"], data[-1][1]["close"]
            return (last - prev) / prev

        alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
        history = alpha_history_node(alpha, window=30)

        # Fan-in example: combine two upstream nodes [history, price]
        # to gate long signals when short-term price momentum is negative.
        def alpha_with_trend_gate(view):
            hist_data = view[history][history.interval]
            price_data = view[price][price.interval]
            if not hist_data or not price_data:
                return None
            # Latest alpha history window produced upstream (list[float])
            hist_series = hist_data[-1][1]
            # Simple 2-sample momentum on close price
            closes = [row[1]["close"] for row in price_data]
            if len(closes) < 2:
                return hist_series
            trend_up = closes[-1] >= closes[-2]
            if trend_up:
                return hist_series
            # Gate: zero-out positive alpha entries when trend is down
            return [v if v <= 0.0 else 0.0 for v in hist_series]

        combined = Node(
            input=[history, price],  # multiple upstreams (fan-in)
            compute_fn=alpha_with_trend_gate,
            name="alpha_with_trend_gate",
            interval=history.interval,
            period=history.period,
        )

        signal = TradeSignalGeneratorNode(
            combined, long_threshold=0.0, short_threshold=0.0
        )
        orders = TradeOrderPublisherNode(signal)

        # Route orders by symbol: simple example mapping suffix to exchange name
        def route_fn(order: dict) -> str:
            sym = order.get("symbol", "") or ""
            return "binance" if str(sym).upper().endswith("USDT") else "ibkr"

        routed = RouterNode(orders, route_fn=route_fn)
        batches = MicroBatchNode(routed)
        self.add_nodes([price, alpha, history, combined, signal, orders, routed, batches])


if __name__ == "__main__":
    service = TradeExecutionService("http://broker")
    Runner.set_trade_execution_service(service)
    Runner.set_trade_order_http_url("http://endpoint")
    Runner.set_trade_order_kafka_topic("orders")
    Runner.offline(OrderPipelineStrategy)
