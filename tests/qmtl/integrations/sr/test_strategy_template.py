"""Tests for expression-based strategy template."""

import pytest

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

    def test_build_from_dag_spec_requires_history_provider(self):
        dag_spec = ExpressionDagSpec(
            nodes=[
                {"id": "n0", "node_type": "input", "label": "input:x"},
            ],
            edges=[],
            output="n0",
            expression_key="abc123",
            equation="x",
            complexity=1,
            loss=0.0,
            node_count=1,
            spec_version="v1",
            data_spec={"dataset_id": "ohlcv"},
        )
        with pytest.raises(ValueError):
            build_strategy_from_dag_spec(dag_spec, history_provider=None)

    def test_build_from_dag_spec_wires_nodes(self):
        dag_spec = ExpressionDagSpec(
            nodes=[
                {"id": "n0", "node_type": "input", "label": "input:price"},
                {
                    "id": "n1",
                    "node_type": "math/add",
                    "label": "add",
                    "inputs": ["n0", "n0"],
                    "params": {},
                },
            ],
            edges=[("n0", "n1"), ("n0", "n1")],
            output="n1",
            expression_key="abc123",
            equation="x + x",
            complexity=2,
            loss=0.0,
            node_count=2,
            spec_version="v1",
            data_spec={
                "dataset_id": "ohlcv",
                "snapshot_version": "2025-01-01",
                "interval": "1m",
                "period": 20,
            },
        )
        provider = object()
        strategy_cls = build_strategy_from_dag_spec(
            dag_spec, history_provider=provider, sr_engine="pysr"
        )
        strat = strategy_cls()
        strat.setup()
        assert len(strat.nodes) == 2
        stream = strat.nodes[0]
        add_node = strat.nodes[1]
        assert getattr(stream, "history_provider", None) is provider
        assert getattr(stream, "dataset_fingerprint", None) == "ohlcv:2025-01-01"
        assert "sr" in getattr(add_node, "tags", [])
        dag = strat.serialize()
        assert dag["meta"]["sr"]["expression_key"] == "abc123"
        assert dag["meta"]["sr"]["data_spec"]["dataset_id"] == "ohlcv"
