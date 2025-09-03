"""Example strategy demonstrating order publication pipeline."""

from qmtl.sdk import Strategy, StreamInput, Node, Runner, TradeExecutionService
from qmtl.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)


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
        signal = TradeSignalGeneratorNode(
            history, long_threshold=0.0, short_threshold=0.0
        )
        orders = TradeOrderPublisherNode(signal)
        self.add_nodes([price, alpha, history, signal, orders])


if __name__ == "__main__":
    service = TradeExecutionService("http://broker")
    Runner.set_trade_execution_service(service)
    Runner.set_trade_order_http_url("http://endpoint")
    Runner.set_trade_order_kafka_topic("orders")
    Runner.offline(OrderPipelineStrategy)
