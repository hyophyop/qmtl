from pathlib import Path
import json
import logging
import pytest
import yaml

from qmtl.config import load_config, UnifiedConfig


def test_load_unified_config_yaml(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "redis_dsn": "redis://test:6379",
        },
        "dagmanager": {
            "neo4j_dsn": "bolt://db:7687",
            "neo4j_breaker_threshold": 5,
            "neo4j_breaker_timeout": 2.0,
        },
    }
    config_file = tmp_path / "cfg.yml"
    config_file.write_text(yaml.safe_dump(data))
    config = load_config(str(config_file))
    assert config.gateway.redis_dsn == data["gateway"]["redis_dsn"]
    assert config.dagmanager.neo4j_dsn == data["dagmanager"]["neo4j_dsn"]
    assert config.dagmanager.neo4j_breaker_threshold == 5
    assert not hasattr(config.dagmanager, "neo4j_breaker_timeout")


def test_load_unified_config_json(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "host": "127.0.0.1",
        },
        "dagmanager": {
            "grpc_port": 1234,
            "neo4j_breaker_threshold": 2,
            "neo4j_breaker_timeout": 1.0,
        },
    }
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps(data))
    config = load_config(str(config_file))
    assert config.gateway.host == "127.0.0.1"
    assert config.dagmanager.grpc_port == 1234
    assert config.dagmanager.neo4j_breaker_threshold == 2
    assert not hasattr(config.dagmanager, "neo4j_breaker_timeout")


def test_load_unified_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("missing.yml")


def test_load_unified_config_directory(tmp_path: Path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    with pytest.raises(OSError):
        load_config(str(d))


def test_load_unified_config_malformed(tmp_path: Path) -> None:
    config_file = tmp_path / "bad.yml"
    config_file.write_text("- 1")
    with pytest.raises(TypeError):
        load_config(str(config_file))


def test_load_unified_config_yaml_error(tmp_path: Path, caplog) -> None:
    config_file = tmp_path / "bad.yml"
    config_file.write_text(":\n  -")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="Failed to parse configuration file"):
            load_config(str(config_file))


def test_load_unified_config_defaults(tmp_path: Path) -> None:
    """Empty files should load default configs."""
    config_file = tmp_path / "empty.yml"
    config_file.write_text("{}")
    config = load_config(str(config_file))
    assert isinstance(config, UnifiedConfig)
    assert config.gateway.redis_dsn is None
    assert config.dagmanager.grpc_port == 50051
    assert config.dagmanager.neo4j_breaker_threshold == 3
    assert not hasattr(config.dagmanager, "neo4j_breaker_timeout")


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
