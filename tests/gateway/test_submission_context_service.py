from __future__ import annotations

import pytest

from qmtl.common.compute_context import DowngradeReason
from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.submission.context_service import (
    ComputeContextService,
    StrategyComputeContext,
)


def _make_payload(**meta_overrides) -> StrategySubmit:
    meta = {
        "execution_domain": "live",
        "as_of": "2024-01-01T00:00:00Z",
        "partition": "tenant-a",
        "dataset_fingerprint": "lake:abc",
    }
    meta.update(meta_overrides)
    return StrategySubmit(
        dag_json="{}",
        meta=meta,
        world_id="world-1",
        world_ids=["world-1", "world-2"],
        node_ids_crc32=0,
    )


def test_build_returns_unique_worlds() -> None:
    service = ComputeContextService()
    payload = _make_payload()

    strategy_ctx = service.build(payload)

    assert isinstance(strategy_ctx, StrategyComputeContext)
    assert strategy_ctx.context.world_id == "world-1"
    assert strategy_ctx.worlds_list() == ["world-1", "world-2"]
    payload_dict = strategy_ctx.commit_log_payload()
    mapping = strategy_ctx.redis_mapping()
    assert payload_dict["execution_domain"] == "live"
    assert mapping["compute_execution_domain"] == "live"


def test_build_handles_missing_as_of() -> None:
    service = ComputeContextService()
    payload = _make_payload(as_of=None, execution_domain="dryrun")

    strategy_ctx = service.build(payload)
    payload_dict = strategy_ctx.commit_log_payload()

    assert strategy_ctx.execution_domain == "backtest"
    assert strategy_ctx.downgraded is True
    assert strategy_ctx.downgrade_reason == DowngradeReason.MISSING_AS_OF
    assert payload_dict["safe_mode"] is True


def test_build_without_worlds() -> None:
    service = ComputeContextService()
    payload = StrategySubmit(
        dag_json="{}",
        meta=None,
        world_id=None,
        node_ids_crc32=0,
    )

    strategy_ctx = service.build(payload)
    payload_dict = strategy_ctx.commit_log_payload()
    mapping = strategy_ctx.redis_mapping()

    assert strategy_ctx.context.world_id == ""
    assert strategy_ctx.worlds_list() == []
    assert mapping == {}
    assert payload_dict["execution_domain"] in {None, ""}

