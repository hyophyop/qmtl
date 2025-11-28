"""Tests for expression-based strategy template."""

import pytest

from qmtl.integrations.sr import (
    ValidationSample,
    ValidationSampleMismatch,
    build_expression_strategy,
    build_strategy_from_dag_spec,
    submit_with_validation,
    validate_strategy_against_sample,
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
        sr_meta = dag["meta"]["sr"]
        assert sr_meta["data_spec"]["dataset_id"] == "ohlcv_spot_1m"
        assert sr_meta["sr_engine"] == "pysr"
        assert sr_meta["spec_version"] == "v1"
        assert sr_meta["expression_key_meta"]["value"] == sr_meta["expression_key"]
        assert sr_meta["dedup_policy"]["expression_key"]["on_duplicate"] == "replace"

    def test_dedup_policy_override(self):
        strategy_cls = build_expression_strategy(
            "x + y",
            sr_engine="pysr",
            on_duplicate="reject",
            spec_version="v2",
        )
        sr_meta = strategy_cls().serialize()["meta"]["sr"]

        assert sr_meta["dedup_policy"]["expression_key"]["on_duplicate"] == "reject"
        assert sr_meta["dedup_policy"]["expression_key"]["spec_version"] == "v2"

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
        assert dag["meta"]["sr"]["dedup_policy"]["expression_key"]["on_duplicate"] == "replace"

    def test_submit_with_validation_passes_and_calls_submit(self):
        strategy_cls = build_expression_strategy("x + y")
        sample = {"points": [{"input": {"x": 1, "y": 2}, "expected": 3}]}

        calls: list[dict] = []

        def _submit_stub(target_cls: type, **kwargs: object) -> dict[str, object]:
            calls.append({"cls": target_cls, "kwargs": kwargs})
            return {"status": "submitted"}

        result = submit_with_validation(
            strategy_cls,
            validation_sample=sample,
            submit_fn=_submit_stub,
            world="demo",
        )

        assert result == {"status": "submitted"}
        assert calls and calls[0]["cls"] is strategy_cls
        assert calls[0]["kwargs"].get("world") == "demo"

    def test_submit_with_validation_rejects_mismatch(self):
        strategy_cls = build_expression_strategy("x + y")
        sample = {"points": [{"input": {"x": 1, "y": 2}, "expected": 4}]}

        def _submit_stub(*_: object, **__: object) -> None:  # pragma: no cover - should not be called
            raise AssertionError("submit stub should not be invoked when validation fails")

        with pytest.raises(ValidationSampleMismatch) as excinfo:
            submit_with_validation(strategy_cls, validation_sample=sample, submit_fn=_submit_stub)

        message = str(excinfo.value)
        assert "expected=4" in message
        assert "actual" in message

    def test_validate_strategy_against_sample_respects_epsilon(self):
        strategy_cls = build_expression_strategy("x")
        sample = ValidationSample.parse(
            {
                "points": [{"input": {"x": 1.0}, "expected": 1.02}],
                "epsilon": {"abs": 0.05},
            }
        )

        result = validate_strategy_against_sample(strategy_cls, sample)

        assert result.passed is True
        assert result.mismatches == []
