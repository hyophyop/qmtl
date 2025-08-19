from __future__ import annotations

from qmtl.pipeline import Pipeline

from strategies.dags.alpha_signal_dag import AlphaSignalStrategy


def test_alpha_signal_strategy_executes(monkeypatch) -> None:
    """AlphaSignalStrategy produces trade orders."""
    monkeypatch.setattr(
        "strategies.dags.alpha_signal_dag.load_config", lambda: {}
    )
    strat = AlphaSignalStrategy()
    strat.setup()
    nodes = strat.nodes
    data = nodes[0]
    publisher = nodes[-1]
    pipe = Pipeline(nodes)
    pipe.feed(data, 0, {"value": 42})
    snapshot = publisher.cache._snapshot()
    orders = snapshot.get(publisher.node_id, {}).get(publisher.interval, [])
    assert orders and orders[0][1]["side"] == "BUY"
