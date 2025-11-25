from pathlib import Path
import json
import logging
import pytest
import yaml

from qmtl.foundation.config import load_config, UnifiedConfig


def test_load_unified_config_yaml(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "redis_dsn": "redis://test:6379",
        },
        "dagmanager": {
            "neo4j_dsn": "bolt://db:7687",
            "kafka_breaker_threshold": 4,
            "kafka_breaker_timeout": 1.5,
        },
    }
    config_file = tmp_path / "cfg.yml"
    config_file.write_text(yaml.safe_dump(data))
    # Deprecated breaker keys under dagmanager should now be rejected
    with pytest.raises(TypeError):
        load_config(str(config_file))


def test_load_unified_config_json(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "host": "127.0.0.1",
        },
        "dagmanager": {
            "grpc_port": 1234,
        },
    }
    config_file = tmp_path / "cfg.json"
    config_file.write_text(json.dumps(data))
    config = load_config(str(config_file))
    assert config.gateway.host == "127.0.0.1"
    assert config.dagmanager.grpc_port == 1234
    assert config.present_sections == frozenset({"gateway", "dagmanager"})


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
    assert config.present_sections == frozenset()


def test_load_unified_config_worldservice_server(tmp_path: Path) -> None:
    config_file = tmp_path / "ws.yml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "worldservice": {
                    "dsn": "sqlite:///ws.db",
                    "redis": "redis://localhost:6379/5",
                    "bind": {"host": "127.0.0.1", "port": 9090},
                    "auth": {"tokens": ["secret-token"]},
                }
            }
        )
    )

    config = load_config(str(config_file))
    assert config.worldservice.server is not None
    assert config.worldservice.server.dsn == "sqlite:///ws.db"
    assert config.worldservice.server.redis == "redis://localhost:6379/5"
    assert config.worldservice.server.bind.port == 9090
    assert config.worldservice.server.auth.tokens == ["secret-token"]
    assert config.worldservice.server.compat_rebalance_v2 is False
    assert config.worldservice.server.alpha_metrics_required is False


def test_load_unified_config_worldservice_server_flags(tmp_path: Path) -> None:
    config_file = tmp_path / "ws_flags.yml"
    config_file.write_text(
        yaml.safe_dump(
            {
                "worldservice": {
                    "dsn": "sqlite:///ws.db",
                    "redis": "redis://localhost:6379/5",
                    "compat_rebalance_v2": True,
                    "alpha_metrics_required": True,
                }
            }
        )
    )

    config = load_config(str(config_file))
    assert config.worldservice.server is not None
    assert config.worldservice.server.compat_rebalance_v2 is True
    assert config.worldservice.server.alpha_metrics_required is True


def test_load_unified_config_rejects_aliases(tmp_path: Path) -> None:
    data = {
        "gateway": {
            "redis_url": "redis://test:6379",
        },
        "dagmanager": {
            "neo4j_url": "bolt://db:7687",
        },
    }
    config_file = tmp_path / "cfg.yml"
    config_file.write_text(yaml.safe_dump(data))
    with pytest.raises(TypeError):
        load_config(str(config_file))


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
