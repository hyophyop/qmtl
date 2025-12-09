from __future__ import annotations

import pytest

from qmtl.runtime.sdk import Runner
from qmtl.runtime.sdk.evaluation_runs import EvaluationRunStatus
from qmtl.runtime.sdk.services import RunnerServices


class _ReadyAfterSecondCallClient:
    def __init__(self) -> None:
        self.calls = 0

    async def get_evaluation_run(self, *, gateway_url: str, world_id: str, strategy_id: str, run_id: str):
        self.calls += 1
        if self.calls == 1:
            return None
        return {
            "summary": {"status": "pass", "recommended_stage": "paper_only"},
            "metrics": {"returns": {"sharpe": 1.23}},
        }


class _CapturingClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_kwargs: dict | None = None

    async def get_evaluation_run(self, **kwargs):
        self.last_kwargs = kwargs
        return self.payload


class _EmptyClient:
    async def get_evaluation_run(self, **kwargs):
        return {"summary": {}}


def _with_services(client):
    original = Runner.services()
    Runner.set_services(RunnerServices(gateway_client=client))
    return original


@pytest.mark.asyncio
async def test_wait_for_evaluation_async_returns_status() -> None:
    client = _ReadyAfterSecondCallClient()
    original = _with_services(client)
    try:
        status = await Runner.wait_for_evaluation_async(
            world="demo",
            run_id="run-1",
            strategy_id="strat-1",
            gateway_url="http://gw",
            timeout=1.0,
            interval=0.0,
        )
    finally:
        Runner.set_services(original)

    assert isinstance(status, EvaluationRunStatus)
    assert status.status == "pass"
    assert status.recommended_stage == "paper_only"
    assert status.metrics["returns"]["sharpe"] == 1.23
    assert client.calls == 2


@pytest.mark.asyncio
async def test_wait_for_evaluation_accepts_full_url() -> None:
    payload = {"summary": {"status": "warn"}, "metrics": {"returns": {}}}
    client = _CapturingClient(payload)
    original = _with_services(client)
    run_url = "https://gw.example.com/api/worlds/world-x/strategies/strat-y/runs/run-99"

    try:
        status = await Runner.wait_for_evaluation_async(
            world=None,
            run_id=run_url,
            strategy_id=None,
            timeout=0.5,
            interval=0.0,
        )
    finally:
        Runner.set_services(original)

    assert client.last_kwargs is not None
    assert client.last_kwargs["gateway_url"] == "https://gw.example.com/api"
    assert client.last_kwargs["world_id"] == "world-x"
    assert client.last_kwargs["strategy_id"] == "strat-y"
    assert client.last_kwargs["run_id"] == "run-99"
    assert status.world_id == "world-x"
    assert status.run_id == "run-99"


@pytest.mark.asyncio
async def test_wait_for_evaluation_times_out_when_not_ready() -> None:
    client = _EmptyClient()
    original = _with_services(client)

    try:
        with pytest.raises(TimeoutError):
            await Runner.wait_for_evaluation_async(
                world="demo",
                run_id="run-timeout",
                strategy_id="strat-timeout",
                gateway_url="http://gw",
                timeout=0.01,
                interval=0.0,
            )
    finally:
        Runner.set_services(original)


@pytest.mark.asyncio
async def test_wait_for_evaluation_requires_strategy_id() -> None:
    client = _EmptyClient()
    original = _with_services(client)

    try:
        with pytest.raises(ValueError):
            await Runner.wait_for_evaluation_async(
                world="demo",
                run_id="missing-strategy",
                strategy_id=None,
                gateway_url="http://gw",
                timeout=0.01,
                interval=0.0,
            )
    finally:
        Runner.set_services(original)
