from pathlib import Path
import json
import pytest
import yaml

from qmtl.gateway.config import load_gateway_config, GatewayConfig


def test_load_gateway_config_yaml(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://test:6379",
        "database_backend": "postgres",
        "database_dsn": "postgresql://db/test",
        "queue_backend": "memory",
    }
    config_file = tmp_path / "gw.yaml"
    config_file.write_text(yaml.safe_dump(data))
    config = load_gateway_config(str(config_file))
    assert config.redis_dsn == data["redis_dsn"]
    assert config.database_backend == "postgres"
    assert config.database_dsn == data["database_dsn"]
    assert config.queue_backend == "memory"


def test_load_gateway_config_json(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://j:6379",
        "database_backend": "memory",
        "database_dsn": "sqlite:///:memory:",
        "queue_backend": "redis",
    }
    config_file = tmp_path / "gw.json"
    config_file.write_text(json.dumps(data))
    config = load_gateway_config(str(config_file))
    assert config.database_backend == "memory"
    assert config.database_dsn == data["database_dsn"]
    assert config.queue_backend == "redis"


def test_load_gateway_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_gateway_config("nope.yml")


def test_load_gateway_config_malformed(tmp_path: Path):
    p = tmp_path / "bad.yml"
    p.write_text("- 1")
    with pytest.raises(TypeError):
        load_gateway_config(str(p))


def test_gateway_config_defaults() -> None:
    cfg = GatewayConfig()
    assert cfg.database_backend == "sqlite"
    assert cfg.database_dsn == "./qmtl.db"
    assert cfg.queue_backend == "memory"
