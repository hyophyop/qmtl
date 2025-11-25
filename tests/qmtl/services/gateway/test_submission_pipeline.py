from __future__ import annotations

import pytest

from qmtl.foundation.common.compute_context import ComputeContext
from typing import Any
from qmtl.services.gateway.submission import (
    PreparedSubmission,
    StrategyComputeContext,
    SubmissionPipeline,
)
from qmtl.services.gateway.submission.diff_executor import DiffOutcome


class _Loader:
    def __init__(self) -> None:
        self.called = False

    def load(self, dag_json: str):
        self.called = True
        class _Loaded:
            dag = {"schema_version": "v1", "nodes": ["n"]}
        return _Loaded()


class _Validator:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, object], int]] = []

    def validate(self, dag: dict[str, object], crc: int):
        self.calls.append((dag, crc))
        class _Report:
            computed_checksum = 0

        return _Report()


class _ContextService:
    async def build(self, payload):
        context = ComputeContext(world_id="w1", execution_domain="live")
        return StrategyComputeContext(context=context, worlds=("w1",))


class _DiffExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(self, **kwargs: object):
        self.calls.append(kwargs)
        return DiffOutcome(
            sentinel_id="sentinel",
            queue_map={"nid": [{"queue": "q", "global": False}]},
        )


class _QueueMapResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], list[str], str | None, str | None]] = []

    async def build(
        self,
        dag: dict[str, Any],
        worlds: list[str],
        default_world: str | None,
        execution_domain: str | None,
    ):
        self.calls.append((dag, worlds, default_world, execution_domain))
        return {"nid": []}


class _Payload:
    dag_json = '{"schema_version": "v1", "nodes": []}'
    node_ids_crc32 = 0


@pytest.mark.asyncio
async def test_pipeline_prepare_and_diff(monkeypatch):
    loader = _Loader()
    validator = _Validator()
    context_service = _ContextService()
    diff_exec = _DiffExecutor()
    resolver = _QueueMapResolver()

    pipeline = SubmissionPipeline(
        dagmanager=None,
        dag_loader=loader,
        node_validator=validator,
        context_service=context_service,
        diff_executor=diff_exec,
        queue_map_resolver=resolver,
    )

    prepared = await pipeline.prepare(_Payload())
    assert isinstance(prepared, PreparedSubmission)
    assert prepared.dag == {"schema_version": "v1", "nodes": ["n"]}
    assert prepared.compute_context.execution_domain == "live"
    assert prepared.worlds == ["w1"]
    assert prepared.node_ids_crc32 == 0
    assert validator.calls

    outcome = await pipeline.run_diff(
        strategy_id="sid",
        dag_json='{"schema_version": "v1", "nodes": []}',
        worlds=["w1"],
        fallback_world_id=None,
        compute_ctx=prepared.compute_context,
        timeout=0.1,
        prefer_queue_map=False,
    )
    assert outcome.sentinel_id == "sentinel"
    assert outcome.queue_map == {"nid": [{"queue": "q", "global": False}]}
    assert diff_exec.calls
    assert diff_exec.calls[0].get("expected_crc32") is None

    result = await pipeline.build_queue_map(prepared.dag, ["w1"], "w1", "live")
    assert result == {"nid": []}
    assert resolver.calls
