"""Tests for expression-based strategy template."""

from qmtl.integrations.sr.strategy_template import (
    build_expression_strategy,
    build_strategy_from_dag_spec,
)
from qmtl.integrations.sr.dag import ExpressionDagSpec


class TestStrategyTemplate:
    """Expression strategy template behavior."""

    def test_evaluate_expression(self):
        strategy_cls = build_expression_strategy("x + y", strategy_name="TestExpr")
        strat = strategy_cls()
        assert strat.evaluate({"x": 2, "y": 3}) == 5.0

    def test_metadata_on_serialize(self):
        data_spec = {"dataset_id": "ohlcv_spot_1m", "snapshot_version": "2025-01-01"}
        strategy_cls = build_expression_strategy("x", data_spec=data_spec, sr_engine="pysr")
        strat = strategy_cls()
        dag = strat.serialize()
        assert dag["meta"]["sr"]["data_spec"]["dataset_id"] == "ohlcv_spot_1m"
        assert dag["meta"]["sr"]["sr_engine"] == "pysr"
        assert "expression_key" in dag["meta"]["sr"]

    def test_build_from_dag_spec(self):
        dag_spec = ExpressionDagSpec(
            nodes=[],
            edges=[],
            output="n0",
            expression_key="abc123",
            equation="x + 1",
            complexity=2,
            loss=0.1,
            node_count=1,
            spec_version="v1",
            data_spec={"dataset_id": "ohlcv"},
        )
        strategy_cls = build_strategy_from_dag_spec(dag_spec, sr_engine="pysr")
        strat = strategy_cls()
        dag = strat.serialize()
        assert dag["meta"]["sr"]["expression"] == "x + 1"
        assert dag["meta"]["sr"]["expression_key"] == "abc123"
        assert dag["meta"]["sr"]["data_spec"]["dataset_id"] == "ohlcv"
