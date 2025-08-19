try:
    from nodes.generators import sample_generator
    from nodes.indicators import sample_indicator
    from nodes.transforms.alpha_performance import AlphaPerformanceNode
    from qmtl.transforms import TradeOrderPublisherNode, TradeSignalGeneratorNode
except ModuleNotFoundError:  # pragma: no cover
    from strategies.nodes.generators import sample_generator
    from strategies.nodes.indicators import sample_indicator
    from strategies.nodes.transforms.alpha_performance import AlphaPerformanceNode
    from qmtl.transforms import TradeOrderPublisherNode, TradeSignalGeneratorNode

from strategies.config import load_config
from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.runner import Runner


class MyStrategy:
    """Custom strategy example for documentation purposes."""

    def __init__(self, config=None):
        self.config = config or load_config()

    def run(self):
        """Run the strategy logic."""
        data = sample_generator()
        metric = sample_indicator(data)
        returns = [metric]

        perf_cfg = self.config.get("performance_metrics", {})
        thresh_cfg = self.config.get("signal_thresholds", {})
        risk_cfg = self.config.get("risk_limits", {})

        history = Node(name="alpha_hist", interval="1s", period=len(returns))
        perf_node = AlphaPerformanceNode(
            history, risk_free_rate=perf_cfg.get("risk_free_rate", 0.0)
        )
        perf_view = CacheView({history.node_id: {history.interval: [(0, returns)]}})
        performance = perf_node.compute_fn(perf_view)
        Runner._postprocess_result(perf_node, performance)

        sig_node = TradeSignalGeneratorNode(
            history,
            long_threshold=thresh_cfg.get("long", 0.0),
            short_threshold=thresh_cfg.get("short", 0.0),
            size=risk_cfg.get("size", 1.0),
            stop_loss=risk_cfg.get("stop_loss"),
            take_profit=risk_cfg.get("take_profit"),
        )
        signal = sig_node.compute_fn(perf_view)
        pub_node = TradeOrderPublisherNode(sig_node, topic="orders")
        sig_view = CacheView({sig_node.node_id: {sig_node.interval: [(0, signal)]}})
        order = pub_node.compute_fn(sig_view)
        Runner._postprocess_result(pub_node, order)

        print(performance)
        print(order)
