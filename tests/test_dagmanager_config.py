from pathlib import Path
import logging
import pytest
import yaml

from qmtl.dagmanager.config import DagManagerConfig, load_dagmanager_config


def test_dagmanager_config_custom_values() -> None:
    cfg = DagManagerConfig(
        neo4j_dsn="bolt://db:7687",
        neo4j_user="neo4j",
        neo4j_password="pw",
        kafka_dsn="localhost:9092",
        kafka_breaker_threshold=5,
    )
    assert cfg.neo4j_dsn == "bolt://db:7687"
    assert cfg.kafka_dsn == "localhost:9092"
    assert cfg.kafka_breaker_threshold == 5


def test_dagmanager_config_defaults() -> None:
    cfg = DagManagerConfig()
    assert cfg.neo4j_dsn is None
    assert cfg.kafka_dsn is None
    assert cfg.kafka_breaker_threshold == 3
    assert not hasattr(cfg, "kafka_breaker_timeout")


def test_load_dagmanager_config_yaml(tmp_path: Path) -> None:
    data = {
        "neo4j_dsn": "bolt://db:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "pw",
        "kafka_dsn": "kafka:9092",
        "grpc_port": 6000,
        "kafka_breaker_timeout": 2.5,
    }
    config_file = tmp_path / "dm.yml"
    config_file.write_text(yaml.safe_dump(data))
    cfg = load_dagmanager_config(str(config_file))
    assert cfg.neo4j_dsn == data["neo4j_dsn"]
    assert cfg.kafka_dsn == "kafka:9092"
    assert cfg.grpc_port == 6000
    assert not hasattr(cfg, "kafka_breaker_timeout")


def test_load_dagmanager_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_dagmanager_config("missing.yml")


def test_load_dagmanager_config_directory(tmp_path: Path) -> None:
    d = tmp_path / "dir"
    d.mkdir()
    with pytest.raises(OSError):
        load_dagmanager_config(str(d))


def test_load_dagmanager_config_yaml_error(tmp_path: Path, caplog) -> None:
    config_file = tmp_path / "bad.yml"
    config_file.write_text(":\n  -")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError, match="Failed to parse configuration file"):
            load_dagmanager_config(str(config_file))

