from __future__ import annotations

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.portfolio import Portfolio
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.watermark import clear_watermarks, get_watermark

from qmtl.runtime.pipeline.execution_nodes.portfolio import PortfolioNode


def test_portfolio_node_updates_positions_and_cash() -> None:
    src = Node(name="fill", interval=1, period=1)
    portfolio = Portfolio(cash=100.0)
    node = PortfolioNode(src, portfolio=portfolio)
    fill = {"symbol": "AAPL", "quantity": 5.0, "fill_price": 10.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, fill)
    assert portfolio.cash == 50.0
    assert out["positions"]["AAPL"]["qty"] == 5.0


def test_portfolio_node_updates_custom_watermark_topic() -> None:
    clear_watermarks()
    src = Node(name="fill", interval=1, period=1)
    src.world_id = "topic-world"
    portfolio = Portfolio(cash=100.0)
    node = PortfolioNode(src, portfolio=portfolio, watermark_topic="custom.topic")
    fill = {"symbol": "AAPL", "quantity": 1.0, "fill_price": 10.0, "timestamp": 200}
    Runner.feed_queue_data(node, src.node_id, 1, 0, fill)
    assert get_watermark("custom.topic", "topic-world") == 200
