import json
from pathlib import Path
import pytest
import yaml

from qmtl.gateway.config import load_gateway_config, GatewayConfig


def test_load_gateway_config_yaml(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://test:6379",
        "database_backend": "postgres",
        "database_dsn": "postgresql://db/test",
        "offline": True,
    }
    cfg_file = tmp_path / "gw.yaml"
    cfg_file.write_text(yaml.safe_dump(data))
    cfg = load_gateway_config(str(cfg_file))
    assert cfg.redis_dsn == data["redis_dsn"]
    assert cfg.database_backend == "postgres"
    assert cfg.database_dsn == data["database_dsn"]
    assert cfg.offline is True


def test_load_gateway_config_json(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://j:6379",
        "database_backend": "memory",
        "database_dsn": "sqlite:///:memory:",
        "offline": False,
    }
    cfg_file = tmp_path / "gw.json"
    cfg_file.write_text(json.dumps(data))
    cfg = load_gateway_config(str(cfg_file))
    assert cfg.database_backend == "memory"
    assert cfg.database_dsn == data["database_dsn"]
    assert cfg.offline is False


def test_load_gateway_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_gateway_config("nope.yml")


def test_load_gateway_config_malformed(tmp_path: Path):
    p = tmp_path / "bad.yml"
    p.write_text("- 1")
    with pytest.raises(TypeError):
        load_gateway_config(str(p))
