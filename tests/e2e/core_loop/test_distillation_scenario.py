from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

from qmtl.runtime.sdk import Runner
from qmtl.runtime.sdk.gateway_client import GatewayClient
from .stack import CoreLoopStackHandle

pytestmark = pytest.mark.contract


def test_distillation_rank_weight_contribution(
    core_loop_stack: CoreLoopStackHandle,
    core_loop_world_id: str,
):
    strategies = _load_distillation_strategies()
    returns = [0.01, -0.02, 0.03, 0.0, 0.015]

    results = []
    for strategy_cls in strategies:
        result = Runner.submit(
            strategy_cls,
            world=core_loop_world_id,
            returns=returns,
        )
        results.append(result)

        assert result.rank is not None
        assert result.weight is not None
        assert result.contribution is not None
        assert result.evaluation_run_id is not None
        assert result.evaluation_run_url is not None
        assert 0.0 <= result.weight <= 1.0
        assert 0.0 <= result.contribution <= 1.0

        run_payload = asyncio.run(
            GatewayClient().get_evaluation_run(
                gateway_url=core_loop_stack.gateway_url,
                world_id=core_loop_world_id,
                strategy_id=result.strategy_id,
                run_id=result.evaluation_run_id,
            )
        )
        assert run_payload is not None
        assert run_payload.get("run_id") == result.evaluation_run_id

    if core_loop_stack.mode == "inproc":
        assert [result.rank for result in results] == [1, 2, 3]


def _load_distillation_strategies():
    root = Path(__file__).resolve().parents[3]
    path = root / "strategies" / "distillation_demo.py"
    spec = importlib.util.spec_from_file_location("distillation_demo", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load strategy module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [
        module.DistillationStrategyAlpha,
        module.DistillationStrategyBeta,
        module.DistillationStrategyGamma,
    ]
