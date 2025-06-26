import json
from pathlib import Path
import yaml

from qmtl.gateway.config import load_gateway_config, GatewayConfig


def test_load_gateway_config_yaml(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://test:6379",
        "database_backend": "postgres",
        "database_dsn": "postgresql://db/test",
    }
    cfg_file = tmp_path / "gw.yaml"
    cfg_file.write_text(yaml.safe_dump(data))
    cfg = load_gateway_config(str(cfg_file))
    assert cfg.redis_dsn == data["redis_dsn"]
    assert cfg.database_backend == "postgres"
    assert cfg.database_dsn == data["database_dsn"]


def test_load_gateway_config_json(tmp_path: Path) -> None:
    data = {
        "redis_dsn": "redis://j:6379",
        "database_backend": "memory",
        "database_dsn": "sqlite:///:memory:",
    }
    cfg_file = tmp_path / "gw.json"
    cfg_file.write_text(json.dumps(data))
    cfg = load_gateway_config(str(cfg_file))
    assert cfg.database_backend == "memory"
    assert cfg.database_dsn == data["database_dsn"]
