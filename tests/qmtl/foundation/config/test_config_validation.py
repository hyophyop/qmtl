from __future__ import annotations

import pytest

from qmtl.foundation.config import UnifiedConfig
from qmtl.foundation.config import DeploymentProfile
from qmtl.foundation.config_validation import (
    _type_description,
    _type_matches,
    _value_type_name,
    validate_gateway_config,
    validate_config_structure,
    validate_dagmanager_config,
    validate_worldservice_config,
)
import qmtl.foundation.config_validation as config_validation
from qmtl.services.dagmanager.config import DagManagerConfig
from qmtl.services.gateway.config import GatewayConfig, GatewayOwnershipConfig
from qmtl.services.worldservice.config import WorldServiceServerConfig


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

    assert results["neo4j"].severity == "warning"
    assert "memory repository" in results["neo4j"].hint
    assert "dev-only" in results["neo4j"].hint
    assert results["kafka"].severity == "warning"
    assert "in-memory queue manager" in results["kafka"].hint
    assert "dev-only" in results["kafka"].hint
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


def test_value_type_name_reports_collections() -> None:
    assert _value_type_name([1, "x"]) == "list[int,str]"
    assert _value_type_name((1,)) == "tuple"
    assert _value_type_name({1, 2}) == "set[int]"
    assert _value_type_name({"a": 1}) == "mapping"


def test_type_description_and_matches_tuple_variants() -> None:
    assert _type_description(list[str]) == "list[str]"
    assert _type_description(tuple[int, ...]) == "tuple[int]"
    assert _type_matches((1, 2, 3), tuple[int, ...]) is True
    assert _type_matches((1, "x"), tuple[int, ...]) is False
    assert _type_matches((1, "x"), tuple[int, str]) is True


@pytest.mark.asyncio
async def test_validate_gateway_worldservice_formats_probe(monkeypatch) -> None:
    config = GatewayConfig(
        worldservice_url="http://world",
        enable_worldservice_proxy=True,
        worldservice_timeout=0.2,
    )

    class Result:
        ok = False
        code = "http_error"
        status = 503
        err = "boom"
        latency_ms = 12.3

    async def _probe(url, service, endpoint, timeout, request):
        return Result()

    monkeypatch.setattr(config_validation, "probe_http_async", _probe)

    issues = await validate_gateway_config(config, offline=False)
    ws_issue = issues["worldservice"]

    assert ws_issue.severity == "error"
    assert "status=503" in ws_issue.hint
    assert "error=boom" in ws_issue.hint
    assert "latency_ms=12.3" in ws_issue.hint


@pytest.mark.asyncio
async def test_validate_gateway_config_requires_persistent_backends_in_prod() -> None:
    config = GatewayConfig()

    issues = await validate_gateway_config(
        config, offline=True, profile=DeploymentProfile.PROD
    )

    assert issues["redis"].severity == "error"
    assert issues["database"].severity == "error"
    assert issues["commitlog"].severity == "error"
    assert issues["ownership"].severity == "ok"
    assert issues["controlbus"].severity == "error"


@pytest.mark.asyncio
async def test_validate_dagmanager_config_requires_backends_in_prod() -> None:
    config = DagManagerConfig()

    issues = await validate_dagmanager_config(
        config, offline=True, profile=DeploymentProfile.PROD
    )

    assert issues["neo4j"].severity == "error"
    assert issues["kafka"].severity == "error"


def test_validate_worldservice_config_enforces_redis_in_prod() -> None:
    issues = validate_worldservice_config(
        WorldServiceServerConfig(dsn="sqlite:///ws.db"),
        profile=DeploymentProfile.PROD,
    )

    assert issues["redis"].severity == "error"


@pytest.mark.asyncio
async def test_validate_gateway_config_reports_kafka_ownership_missing_bootstrap() -> None:
    config = GatewayConfig(
        ownership=GatewayOwnershipConfig(mode="kafka", topic="gateway.ownership"),
    )

    issues = await validate_gateway_config(config, offline=True)

    assert issues["ownership"].severity == "warning"
    assert "bootstrap" in issues["ownership"].hint
