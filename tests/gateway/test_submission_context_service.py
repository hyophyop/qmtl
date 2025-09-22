from __future__ import annotations

import pytest

from qmtl.gateway.models import StrategySubmit
from qmtl.gateway.submission.context_service import ComputeContextService


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

    context, payload_dict, mapping, worlds = service.build(payload)

    assert context.world_id == "world-1"
    assert worlds == ["world-1", "world-2"]
    assert payload_dict["execution_domain"] == "live"
    assert mapping["compute_execution_domain"] == "live"


def test_build_handles_missing_as_of() -> None:
    service = ComputeContextService()
    payload = _make_payload(as_of=None, execution_domain="dryrun")

    context, payload_dict, _, _ = service.build(payload)

    assert context.execution_domain == "backtest"
    assert context.downgraded is True
    assert payload_dict["safe_mode"] is True


def test_build_without_worlds() -> None:
    service = ComputeContextService()
    payload = StrategySubmit(
        dag_json="{}",
        meta=None,
        world_id=None,
        node_ids_crc32=0,
    )

    context, payload_dict, mapping, worlds = service.build(payload)
    assert context.world_id == ""
    assert worlds == []
    assert mapping == {}
    assert payload_dict["execution_domain"] in {None, ""}

