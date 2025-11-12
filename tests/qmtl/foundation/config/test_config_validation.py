from __future__ import annotations

import pytest

from qmtl.foundation.config import UnifiedConfig
from qmtl.foundation.config_validation import (
    validate_config_structure,
    validate_dagmanager_config,
)
from qmtl.services.dagmanager.config import DagManagerConfig


@pytest.mark.asyncio
async def test_validate_dagmanager_config_offline_skips_services() -> None:
    config = DagManagerConfig(
        neo4j_dsn="bolt://neo4j",
        kafka_dsn="kafka:9092",
        controlbus_dsn="kafka:9093",
        controlbus_queue_topic="dag-events",
    )

    results = await validate_dagmanager_config(config, offline=True)

    assert results["neo4j"].severity == "warning"
    assert "Offline mode" in results["neo4j"].hint
    assert results["kafka"].severity == "warning"
    assert "Offline mode" in results["kafka"].hint
    assert results["controlbus"].severity == "warning"
    assert "Offline mode" in results["controlbus"].hint


@pytest.mark.asyncio
async def test_validate_dagmanager_config_skips_missing_services() -> None:
    results = await validate_dagmanager_config(DagManagerConfig(), offline=False)

    assert results["neo4j"].severity == "ok"
    assert "memory repository" in results["neo4j"].hint
    assert results["kafka"].severity == "ok"
    assert "in-memory queue manager" in results["kafka"].hint
    assert results["controlbus"].severity == "ok"


def test_validate_config_structure_reports_list_schemas() -> None:
    unified = UnifiedConfig()
    unified.cache.feature_artifact_write_domains = "not-a-list"

    issues = validate_config_structure(unified)
    cache_issue = issues["cache"]

    assert cache_issue.severity == "error"
    assert "feature_artifact_write_domains" in cache_issue.hint
    assert "expected list[str]" in cache_issue.hint
    assert "got str" in cache_issue.hint
