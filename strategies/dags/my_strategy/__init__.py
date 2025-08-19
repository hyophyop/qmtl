try:
    from nodes.generators import sample_generator
    from nodes.indicators import sample_indicator
    from nodes.transforms.alpha_performance import alpha_performance_node
    from nodes.transforms.trade_signal import trade_signal_node
except ModuleNotFoundError:  # pragma: no cover
    from strategies.nodes.generators import sample_generator
    from strategies.nodes.indicators import sample_indicator
    from strategies.nodes.transforms.alpha_performance import alpha_performance_node
    from strategies.nodes.transforms.trade_signal import trade_signal_node

from strategies.config import load_config


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

        performance = alpha_performance_node(
            returns, risk_free_rate=perf_cfg.get("risk_free_rate", 0.0)
        )
        signal = trade_signal_node(
            returns,
            long_threshold=thresh_cfg.get("long", 0.0),
            short_threshold=thresh_cfg.get("short", 0.0),
            size=risk_cfg.get("size", 1.0),
            stop_loss=risk_cfg.get("stop_loss"),
            take_profit=risk_cfg.get("take_profit"),
        )

        print(performance)
        print(signal)
