from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from qmtl.foundation.config import (
    DeploymentProfile,
    SeamlessConfig,
    UnifiedConfig,
    load_config,
)
from qmtl.foundation.config_validation import (
    _type_description,
    _type_matches,
    _value_type_name,
    validate_gateway_config,
    validate_config_structure,
    validate_dagmanager_config,
    validate_seamless_config,
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
    assert results["controlbus"].severity == "warning"
    assert "ControlBus disabled" in results["controlbus"].hint


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
    assert issues["controlbus"].severity == "error"


def test_validate_worldservice_config_enforces_redis_in_prod() -> None:
    issues = validate_worldservice_config(
        WorldServiceServerConfig(dsn="sqlite:///ws.db"),
        profile=DeploymentProfile.PROD,
    )

    assert issues["dsn"].severity == "ok"
    assert issues["redis"].severity == "error"
    assert issues["controlbus"].severity == "error"


def test_validate_worldservice_config_allows_missing_controlbus_in_dev() -> None:
    issues = validate_worldservice_config(
        WorldServiceServerConfig(dsn="sqlite:///ws.db"),
        profile=DeploymentProfile.DEV,
    )

    assert issues["dsn"].severity == "ok"
    assert issues["controlbus"].severity == "warning"
    assert "ControlBus disabled" in issues["controlbus"].hint


def test_validate_worldservice_config_requires_server_in_prod() -> None:
    issues = validate_worldservice_config(None, profile=DeploymentProfile.PROD)

    assert issues["server"].severity == "error"
    assert "worldservice.server" in issues["server"].hint


@pytest.mark.asyncio
async def test_validate_gateway_config_reports_kafka_ownership_missing_bootstrap() -> None:
    config = GatewayConfig(
        ownership=GatewayOwnershipConfig(mode="kafka", topic="gateway.ownership"),
    )

    issues = await validate_gateway_config(config, offline=True)

    assert issues["ownership"].severity == "warning"
    assert "bootstrap" in issues["ownership"].hint


@pytest.mark.asyncio
async def test_validate_seamless_config_warns_when_url_missing_in_dev() -> None:
    issues = await validate_seamless_config(
        SeamlessConfig(),
        offline=False,
        profile=DeploymentProfile.DEV,
    )

    assert issues["coordinator_url"].severity == "warning"
    assert "in-memory" in issues["coordinator_url"].hint


@pytest.mark.asyncio
async def test_validate_seamless_config_errors_without_url_in_prod() -> None:
    issues = await validate_seamless_config(
        SeamlessConfig(),
        offline=False,
        profile=DeploymentProfile.PROD,
    )

    assert issues["coordinator_url"].severity == "error"
    assert "seamless.coordinator_url" in issues["coordinator_url"].hint


@pytest.mark.asyncio
async def test_validate_seamless_config_reports_health_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, str] = {}

    class Result:
        ok = False
        code = "TIMEOUT"
        status = None
        err = "timeout"
        latency_ms = 123.4

    async def _probe(url: str, *, attempts: int, backoff_seconds: float, timeout_seconds: float):
        called["url"] = url
        called["attempts"] = str(attempts)
        called["backoff"] = str(backoff_seconds)
        called["timeout"] = str(timeout_seconds)
        return Result()

    monkeypatch.setattr(config_validation, "probe_coordinator_health_async", _probe)

    issues = await validate_seamless_config(
        SeamlessConfig(coordinator_url="http://coord"),
        offline=False,
        profile=DeploymentProfile.PROD,
    )

    assert issues["health"].severity == "error"
    assert "code=TIMEOUT" in issues["health"].hint
    assert called["url"] == "http://coord"


@pytest.mark.asyncio
async def test_validate_seamless_config_requires_backends_in_prod() -> None:
    issues = await validate_seamless_config(
        SeamlessConfig(coordinator_url="http://coord"),
        offline=True,
        profile=DeploymentProfile.PROD,
    )

    assert issues["redis_dsn"].severity == "error"
    assert issues["questdb_dsn"].severity == "error"
    assert issues["artifact_endpoint"].severity == "error"
    assert issues["artifact_bucket"].severity == "error"


@pytest.mark.asyncio
async def test_validate_seamless_config_warns_backends_in_dev() -> None:
    issues = await validate_seamless_config(
        SeamlessConfig(coordinator_url="http://coord"),
        offline=True,
        profile=DeploymentProfile.DEV,
    )

    assert issues["redis_dsn"].severity == "warning"
    assert issues["questdb_dsn"].severity == "warning"
    assert issues["artifact_endpoint"].severity == "warning"
    assert issues["artifact_bucket"].severity == "warning"


@pytest.mark.asyncio
async def test_validate_seamless_config_checks_connectivity(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Redis:
        async def ping(self):
            return "PONG"

        async def close(self):
            return None

    class _Conn:
        async def close(self):
            return None

    class _ProbeResult:
        ok = True
        code = "OK"
        status = 200
        err = None
        latency_ms = 2.0

    async def _probe(*_args, **_kwargs):
        return _ProbeResult()

    async def _questdb_conn(_dsn):
        return _Conn()

    async def _probe_coordinator(url, **_kwargs):
        return _ProbeResult()

    monkeypatch.setattr(config_validation, "create_redis_client", lambda dsn: _Redis())
    monkeypatch.setattr(config_validation, "open_asyncpg_connection", _questdb_conn)
    monkeypatch.setattr(config_validation, "probe_coordinator_health_async", _probe_coordinator)
    monkeypatch.setattr(config_validation, "probe_http_async", _probe)

    issues = await validate_seamless_config(
        SeamlessConfig(
            coordinator_url="http://coord",
            redis_dsn="redis://localhost:6379/3",
            questdb_dsn="postgresql://localhost:8812/qmtl",
            artifact_endpoint="http://minio:9000",
            artifact_bucket="qmtl",
        ),
        offline=False,
        profile=DeploymentProfile.PROD,
    )

    assert issues["redis_dsn"].severity == "ok"
    assert issues["questdb_dsn"].severity == "ok"
    assert issues["artifact_endpoint"].severity == "ok"
    assert issues["artifact_bucket"].severity == "ok"


@pytest.mark.asyncio
async def test_validate_seamless_config_reports_connectivity_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ProbeResult:
        ok = False
        code = "NETWORK"
        status = None
        err = "down"
        latency_ms = 1.0

    async def _probe(*_args, **_kwargs):
        return _ProbeResult()

    async def _broken_connection(_dsn):
        raise RuntimeError("questdb down")

    class _Redis:
        async def ping(self):
            raise RuntimeError("redis down")

        async def close(self):
            return None

    async def _probe_coordinator(url, **_kwargs):
        return _ProbeResult()

    monkeypatch.setattr(config_validation, "create_redis_client", lambda dsn: _Redis())
    monkeypatch.setattr(config_validation, "open_asyncpg_connection", _broken_connection)
    monkeypatch.setattr(config_validation, "probe_coordinator_health_async", _probe_coordinator)
    monkeypatch.setattr(config_validation, "probe_http_async", _probe)

    issues = await validate_seamless_config(
        SeamlessConfig(
            coordinator_url="http://coord",
            redis_dsn="redis://localhost:6379/3",
            questdb_dsn="postgresql://localhost:8812/qmtl",
            artifact_endpoint="http://minio:9000",
            artifact_bucket="qmtl",
        ),
        offline=False,
        profile=DeploymentProfile.PROD,
    )

    assert issues["redis_dsn"].severity == "error"
    assert "redis down" in issues["redis_dsn"].hint
    assert issues["questdb_dsn"].severity == "error"
    assert "questdb down" in issues["questdb_dsn"].hint
    assert issues["artifact_endpoint"].severity == "error"
    assert "code=NETWORK" in issues["artifact_endpoint"].hint
    assert issues["artifact_bucket"].severity == "ok"


@pytest.mark.asyncio
async def test_maximal_template_validates_in_prod_profile() -> None:
    template = Path("qmtl/examples/templates/config/qmtl.maximal.yml")

    unified = load_config(str(template))

    assert unified.profile is DeploymentProfile.PROD
    assert unified.gateway.commitlog_bootstrap

    issues = await validate_gateway_config(
        unified.gateway, offline=True, profile=unified.profile
    )

    assert issues["commitlog"].severity == "ok"


@pytest.mark.asyncio
async def test_backend_stack_template_enforces_prod_commitlog(tmp_path) -> None:
    template = Path("qmtl/examples/templates/backend_stack.example.yml")
    data = yaml.safe_load(template.read_text())
    assert data["profile"] == "prod"

    baseline_path = tmp_path / "baseline.yml"
    baseline_path.write_text(yaml.safe_dump(data))
    unified = load_config(str(baseline_path))

    issues = await validate_gateway_config(
        unified.gateway, offline=True, profile=DeploymentProfile.PROD
    )
    assert issues["commitlog"].severity == "ok"

    missing = copy.deepcopy(data)
    missing["gateway"]["commitlog_bootstrap"] = None
    missing_path = tmp_path / "missing.yml"
    missing_path.write_text(yaml.safe_dump(missing))

    missing_cfg = load_config(str(missing_path))
    missing_issues = await validate_gateway_config(
        missing_cfg.gateway, offline=True, profile=DeploymentProfile.PROD
    )

    assert missing_issues["commitlog"].severity == "error"
