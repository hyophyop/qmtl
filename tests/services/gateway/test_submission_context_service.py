import pytest

from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.submission.context_service import (
    ComputeContextService,
    StrategyComputeContext,
)


class _StubWorldClient:
    def __init__(self, payload, *, stale: bool = False, fail: bool = False) -> None:
        self._payload = payload
        self._stale = stale
        self._fail = fail
        self.calls: list[str] = []

    async def get_decide(self, world_id: str):
        self.calls.append(world_id)
        if self._fail:
            raise RuntimeError("worldservice down")
        return self._payload, self._stale


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


@pytest.mark.asyncio
async def test_build_uses_worldservice_decision() -> None:
    client = _StubWorldClient(
        {
            "effective_mode": "paper",
            "as_of": "2024-02-01T00:00:00Z",
            "dataset_fingerprint": "lake:ws",
        }
    )
    service = ComputeContextService(world_client=client)
    payload = _make_payload(partition="tenant-b", dataset_fingerprint="lake:override")

    strategy_ctx = await service.build(payload)

    assert isinstance(strategy_ctx, StrategyComputeContext)
    assert strategy_ctx.context.world_id == "world-1"
    # Execution domain derived from effective_mode -> paper => dryrun
    assert strategy_ctx.execution_domain == "dryrun"
    # As-of prefers WorldService decision when provided
    assert strategy_ctx.as_of == "2024-02-01T00:00:00Z"
    # Partition override from submission meta is retained
    assert strategy_ctx.partition == "tenant-b"
    assert strategy_ctx.dataset_fingerprint == "lake:ws"
    assert strategy_ctx.worlds_list() == ["world-1", "world-2"]


@pytest.mark.asyncio
async def test_build_handles_missing_as_of_without_worldservice() -> None:
    service = ComputeContextService()
    payload = _make_payload(as_of=None, execution_domain="dryrun")

    strategy_ctx = await service.build(payload)

    assert strategy_ctx.execution_domain == "backtest"
    assert strategy_ctx.downgraded is True
    assert strategy_ctx.downgrade_reason == DowngradeReason.MISSING_AS_OF
    assert strategy_ctx.safe_mode is True


@pytest.mark.asyncio
async def test_build_marks_safe_mode_on_stale_decision() -> None:
    client = _StubWorldClient(
        {"effective_mode": "live", "as_of": "2024-02-01T00:00:00Z"},
        stale=True,
    )
    service = ComputeContextService(world_client=client)
    payload = _make_payload()

    strategy_ctx = await service.build(payload)

    assert strategy_ctx.execution_domain == "backtest"
    assert strategy_ctx.safe_mode is True
    assert strategy_ctx.downgrade_reason == DowngradeReason.STALE_DECISION


@pytest.mark.asyncio
async def test_build_safe_mode_when_worldservice_unavailable() -> None:
    client = _StubWorldClient({}, fail=True)
    service = ComputeContextService(world_client=client)
    payload = _make_payload()

    strategy_ctx = await service.build(payload)

    assert client.calls == ["world-1"]
    assert strategy_ctx.execution_domain == "backtest"
    assert strategy_ctx.safe_mode is True
    assert strategy_ctx.downgraded is True
    assert strategy_ctx.downgrade_reason == DowngradeReason.DECISION_UNAVAILABLE


@pytest.mark.asyncio
async def test_build_preserves_live_domain_without_worldservice() -> None:
    service = ComputeContextService()
    payload = _make_payload()

    strategy_ctx = await service.build(payload)

    assert strategy_ctx.execution_domain == "live"
    assert strategy_ctx.safe_mode is False
    assert strategy_ctx.downgraded is False


@pytest.mark.asyncio
async def test_build_without_worlds() -> None:
    service = ComputeContextService()
    payload = StrategySubmit(
        dag_json="{}",
        meta=None,
        world_id=None,
        node_ids_crc32=0,
    )

    strategy_ctx = await service.build(payload)

    assert strategy_ctx.context.world_id == ""
    assert strategy_ctx.worlds_list() == []
    assert strategy_ctx.redis_mapping() == {
        "compute_execution_domain": "backtest",
        "compute_downgrade_reason": "decision_unavailable",
    }
