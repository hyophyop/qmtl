from pathlib import Path
import json
import logging
import pytest
import yaml

from qmtl.foundation.config import load_config
from qmtl.services.gateway.config import GatewayConfig


def test_load_config_gateway_yaml(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://test:6379",
        "database_backend": "postgres",
        "database_dsn": "postgresql://db/test",
        "insert_sentinel": False,
        "enforce_live_guard": False,
    }
    config_file = tmp_path / "gw.yaml"
    config_file.write_text(yaml.safe_dump({"gateway": data}))
    config = load_config(str(config_file))
    assert config.gateway.redis_dsn == data["redis_dsn"]
    assert config.gateway.database_backend == "postgres"
    assert config.gateway.database_dsn == data["database_dsn"]
    assert config.gateway.insert_sentinel is False
    assert config.gateway.enforce_live_guard is False


def test_load_config_gateway_json(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://j:6379",
        "database_backend": "memory",
        "database_dsn": "sqlite:///:memory:",
        "insert_sentinel": True,
        "enforce_live_guard": True,
    }
    config_file = tmp_path / "gw.json"
    config_file.write_text(json.dumps({"gateway": data}))
    config = load_config(str(config_file))
    assert config.gateway.redis_dsn == data["redis_dsn"]
    assert config.gateway.database_backend == "memory"
    assert config.gateway.database_dsn == data["database_dsn"]
    assert config.gateway.insert_sentinel is True
    assert config.gateway.enforce_live_guard is True


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("nope.yml")


def test_load_config_directory(tmp_path: Path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    with pytest.raises(OSError):
        load_config(str(d))


def test_load_config_malformed(tmp_path: Path) -> None:
    p = tmp_path / "bad.yml"
    p.write_text("- 1")
    with pytest.raises(TypeError):
        load_config(str(p))


def test_load_config_yaml_error(tmp_path: Path, caplog) -> None:
    p = tmp_path / "bad_syntax.yml"
    p.write_text(":\n  -")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="Failed to parse configuration file"):
            load_config(str(p))


def test_gateway_config_defaults() -> None:
    cfg = GatewayConfig()
    assert cfg.redis_dsn is None
    assert cfg.database_backend == "sqlite"
    assert cfg.database_dsn == "./qmtl.db"
    assert cfg.insert_sentinel is True
    assert cfg.worldservice_timeout == 0.3
    assert cfg.worldservice_retries == 2
    assert cfg.enforce_live_guard is True
    assert cfg.rebalance_schema_version == 1
    assert cfg.alpha_metrics_capable is False
    assert cfg.compute_context_contract is None
    assert cfg.ownership.mode == "postgres"
    assert cfg.ownership.topic == "gateway.ownership"
    assert cfg.ownership.group_id == "gateway-ownership"
    caps = cfg.build_health_capabilities()
    assert caps.rebalance_schema_version == 1
    assert caps.alpha_metrics_capable is False
    assert caps.compute_context_contract is None


def test_gateway_config_builds_capabilities_from_values() -> None:
    cfg = GatewayConfig(
        rebalance_schema_version=2,
        alpha_metrics_capable=True,
        compute_context_contract="compute:v2",
    )
    caps = cfg.build_health_capabilities()
    assert caps.rebalance_schema_version == 2
    assert caps.alpha_metrics_capable is True
    assert caps.compute_context_contract == "compute:v2"


def test_gateway_config_parses_ownership_block(tmp_path: Path) -> None:
    ownership = {
        "mode": "kafka",
        "bootstrap": "kafka:9092",
        "topic": "gateway.ownership",
        "group_id": "locks",
        "start_timeout": 1.5,
    }
    config_file = tmp_path / "ownership.yml"
    config_file.write_text(yaml.safe_dump({"gateway": {"ownership": ownership}}))

    config = load_config(str(config_file))

    assert config.gateway.ownership.mode == "kafka"
    assert config.gateway.ownership.bootstrap == "kafka:9092"
    assert config.gateway.ownership.topic == "gateway.ownership"
    assert config.gateway.ownership.group_id == "locks"
    assert config.gateway.ownership.start_timeout == 1.5
