import yaml
import pytest
from pathlib import Path
from qmtl.dagmanager.config import load_dagmanager_config, DagManagerConfig


def test_load_dagmanager_config_yaml(tmp_path: Path) -> None:
    data = {
        "repo_backend": "neo4j",
        "neo4j_dsn": "bolt://db:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "pw",
        "queue_backend": "kafka",
        "kafka_dsn": "localhost:9092",
        "kafka_breaker_threshold": 5,
        "kafka_breaker_timeout": 2.5,
    }
    config_file = tmp_path / "dm.yml"
    config_file.write_text(yaml.safe_dump(data))
    config = load_dagmanager_config(str(config_file))
    assert config.neo4j_dsn == data["neo4j_dsn"]
    assert config.kafka_dsn == data["kafka_dsn"]
    assert config.kafka_breaker_threshold == 5
    assert config.kafka_breaker_timeout == 2.5


def test_load_dagmanager_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_dagmanager_config("nope.yml")


def test_load_dagmanager_config_malformed(tmp_path: Path):
    f = tmp_path / "bad.yml"
    f.write_text("- 1")
    with pytest.raises(TypeError):
        load_dagmanager_config(str(f))


def test_dagmanager_config_defaults() -> None:
    cfg = DagManagerConfig()
    assert cfg.repo_backend == "memory"
    assert cfg.queue_backend == "memory"
    assert cfg.kafka_breaker_threshold == 3
    assert cfg.kafka_breaker_timeout == 60.0

