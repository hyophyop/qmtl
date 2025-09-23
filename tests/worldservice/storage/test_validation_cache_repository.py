from __future__ import annotations

import pytest

from qmtl.services.worldservice.storage.audit import AuditLogRepository
from qmtl.services.worldservice.storage.models import ValidationCacheEntry
from qmtl.services.worldservice.storage.validation_cache import ValidationCacheRepository


@pytest.mark.parametrize("domain", ["BACKTEST", "Backtest", "backtest"])
def test_validation_cache_repository_normalises_domain(domain: str) -> None:
    audit = AuditLogRepository()
    repo = ValidationCacheRepository(audit)

    repo.set(
        "world-1",
        node_id="node-1",
        execution_domain=domain,
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
        result="ok",
        metrics={"latency": 1.0},
    )

    legacy_key = repo._compute_eval_key(  # type: ignore[attr-defined]
        node_id="node-1",
        world_id="world-1",
        execution_domain="backtest",
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
    )
    legacy = ValidationCacheEntry(
        eval_key=legacy_key,
        node_id="node-1",
        execution_domain="BACKTEST",
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
        result="ok",
        metrics={"latency": 1.0},
        timestamp="2024-01-01T00:00:00Z",
    )
    repo.cache.setdefault("world-1", {}).setdefault("node-1", {})["BACKTEST"] = legacy

    entry = repo.get(
        "world-1",
        node_id="node-1",
        execution_domain="backtest",
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
    )
    assert entry is not None
    assert entry.execution_domain == "backtest"
