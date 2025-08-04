import json
from pathlib import Path
import pytest
import yaml

from qmtl.config import load_config, UnifiedConfig


def test_load_unified_config_yaml(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "redis_dsn": "redis://test:6379",
            "dagclient_breaker_threshold": 4,
        },
        "dagmanager": {
            "neo4j_dsn": "bolt://db:7687",
            "neo4j_breaker_threshold": 5,
        },
    }
    config_file = tmp_path / "cfg.yml"
    config_file.write_text(yaml.safe_dump(data))
    config = load_config(str(config_file))
    assert config.gateway.redis_dsn == data["gateway"]["redis_dsn"]
    assert config.gateway.dagclient_breaker_threshold == 4
    assert config.dagmanager.neo4j_dsn == data["dagmanager"]["neo4j_dsn"]
    assert config.dagmanager.neo4j_breaker_threshold == 5


def test_load_unified_config_json(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "host": "127.0.0.1",
            "dagclient_breaker_threshold": 3,
        },
        "dagmanager": {
            "grpc_port": 1234,
            "neo4j_breaker_threshold": 2,
        },
    }
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps(data))
    config = load_config(str(config_file))
    assert config.gateway.host == "127.0.0.1"
    assert config.dagmanager.grpc_port == 1234
    assert config.gateway.dagclient_breaker_threshold == 3
    assert config.dagmanager.neo4j_breaker_threshold == 2


def test_load_unified_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("missing.yml")


def test_load_unified_config_malformed(tmp_path: Path) -> None:
    config_file = tmp_path / "bad.yml"
    config_file.write_text("- 1")
    with pytest.raises(TypeError):
        load_config(str(config_file))


def test_load_unified_config_defaults(tmp_path: Path) -> None:
    """Empty files should load default configs."""
    config_file = tmp_path / "empty.yml"
    config_file.write_text("{}")
    config = load_config(str(config_file))
    assert isinstance(config, UnifiedConfig)
    assert config.gateway.redis_dsn is None
    assert config.dagmanager.grpc_port == 50051
    assert config.gateway.dagclient_breaker_threshold == 3
    assert config.dagmanager.neo4j_breaker_threshold == 3


def test_load_unified_config_bad_gateway(tmp_path: Path) -> None:
    config_file = tmp_path / "bad.yml"
    config_file.write_text(yaml.safe_dump({"gateway": [1, 2, 3]}))
    with pytest.raises(TypeError, match="gateway section must be a mapping"):
        load_config(str(config_file))


def test_load_unified_config_bad_dagmanager(tmp_path: Path) -> None:
    config_file = tmp_path / "bad.yml"
    config_file.write_text(yaml.safe_dump({"dagmanager": [1]}))
    with pytest.raises(TypeError, match="dagmanager section must be a mapping"):
        load_config(str(config_file))
