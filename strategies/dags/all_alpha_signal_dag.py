from __future__ import annotations

"""Strategy DAG aggregating all alpha signals into trade orders."""

from qmtl.sdk import Node, Strategy
from qmtl.transforms import (
    AlphaPerformanceNode,
    TradeOrderPublisherNode,
    TradeSignalGeneratorNode,
    alpha_history_node,
)

from strategies.config import load_config
from strategies.nodes.generators import all_alpha_generator_node
from strategies.nodes.indicators.composite_alpha import composite_alpha_node


class AllAlphaSignalStrategy(Strategy):
    """Pipeline: data → composite alpha → history → performance → signal → order."""

    def setup(self) -> None:  # noqa: D401
        cfg = load_config()
        perf_cfg = cfg.get("performance_metrics", {})
        thresh_cfg = cfg.get("signal_thresholds", {})
        risk_cfg = cfg.get("risk_limits", {})
        streams = cfg.get("streams", []) or [{}]

        nodes: list[Node] = []

        for stream in streams:
            interval = stream.get("interval", "1s")

            data = Node(
                compute_fn=lambda _: all_alpha_generator_node(),
                name="all_alpha_data",
                interval=interval,
                period=1,
            )

            alpha = Node(
                input=data,
                compute_fn=composite_alpha_node,
                name="all_alpha",
                interval=interval,
                period=1,
            )

            history = alpha_history_node(
                alpha,
                window=20,
                select_fn=lambda payload: payload["alpha"],
                name=f"{alpha.name}_history",
            )

            perf = AlphaPerformanceNode(
                history,
                risk_free_rate=perf_cfg.get("risk_free_rate", 0.0),
            )

            signal = TradeSignalGeneratorNode(
                history,
                long_threshold=thresh_cfg.get("long", 0.0),
                short_threshold=thresh_cfg.get("short", 0.0),
                size=risk_cfg.get("size", 1.0),
                stop_loss=risk_cfg.get("stop_loss"),
                take_profit=risk_cfg.get("take_profit"),
            )

            publisher = TradeOrderPublisherNode(signal, topic="orders")

            nodes.extend([data, alpha, history, perf, signal, publisher])

        self.add_nodes(nodes)
