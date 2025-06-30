import json
from pathlib import Path
import pytest
import yaml

from qmtl.config import load_config, UnifiedConfig


def test_load_unified_config_yaml(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "redis_dsn": "redis://test:6379",
        },
        "dagmanager": {
            "neo4j_uri": "bolt://db:7687",
        },
    }
    cfg_file = tmp_path / "cfg.yml"
    cfg_file.write_text(yaml.safe_dump(data))
    cfg = load_config(str(cfg_file))
    assert cfg.gateway.redis_dsn == data["gateway"]["redis_dsn"]
    assert cfg.dagmanager.neo4j_uri == data["dagmanager"]["neo4j_uri"]


def test_load_unified_config_json(tmp_path: Path) -> None:
    data = {
        "gateway": {"host": "127.0.0.1"},
        "dagmanager": {"grpc_port": 1234},
    }
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(json.dumps(data))
    cfg = load_config(str(cfg_file))
    assert cfg.gateway.host == "127.0.0.1"
    assert cfg.dagmanager.grpc_port == 1234


def test_load_unified_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("missing.yml")


def test_load_unified_config_malformed(tmp_path: Path) -> None:
    cfg_file = tmp_path / "bad.yml"
    cfg_file.write_text("- 1")
    with pytest.raises(TypeError):
        load_config(str(cfg_file))
