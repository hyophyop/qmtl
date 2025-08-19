from __future__ import annotations

"""Strategy DAG that derives trade orders from an alpha signal."""

from qmtl.sdk import Strategy, Node
from qmtl.transforms import (
    AlphaPerformanceNode,
    TradeOrderPublisherNode,
    TradeSignalGeneratorNode,
    alpha_history_node,
)

from strategies.config import load_config
from strategies.nodes.generators import sample_generator
from strategies.nodes.indicators import sample_indicator


class AlphaSignalStrategy(Strategy):
    """Pipeline: stream → alpha → history → performance → signal → order."""

    def setup(self) -> None:  # noqa: D401
        cfg = load_config()
        perf_cfg = cfg.get("performance_metrics", {})
        thresh_cfg = cfg.get("signal_thresholds", {})
        risk_cfg = cfg.get("risk_limits", {})
        streams = cfg.get("streams", []) or [{}]

        nodes: list[Node] = []

        for stream in streams:
            symbol = stream.get("symbol", "sample")
            interval = stream.get("interval", "1s")

            # 1. data stream
            data = Node(
                compute_fn=lambda _: sample_generator(),
                name=f"{symbol.lower()}_data",
                interval=interval,
                period=1,
            )

            # 2. alpha calculation
            alpha = Node(
                input=data,
                compute_fn=sample_indicator,
                name=f"{symbol.lower()}_alpha",
                interval=interval,
                period=1,
            )

            # 3. alpha history
            history = alpha_history_node(alpha, window=20, name=f"{alpha.name}_history")

            # 4. performance metrics
            perf = AlphaPerformanceNode(
                history,
                risk_free_rate=perf_cfg.get("risk_free_rate", 0.0),
            )

            # 5. trade signal
            signal = TradeSignalGeneratorNode(
                history,
                long_threshold=thresh_cfg.get("long", 0.0),
                short_threshold=thresh_cfg.get("short", 0.0),
                size=risk_cfg.get("size", 1.0),
                stop_loss=risk_cfg.get("stop_loss"),
                take_profit=risk_cfg.get("take_profit"),
            )

            # 6. order publisher
            publisher = TradeOrderPublisherNode(signal, topic="orders")

            nodes.extend([data, alpha, history, perf, signal, publisher])

        self.add_nodes(nodes)
