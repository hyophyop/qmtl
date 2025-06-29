import yaml
import pytest
from pathlib import Path
from qmtl.dagmanager.config import load_dagmanager_config, DagManagerConfig


def test_load_dagmanager_config_yaml(tmp_path: Path) -> None:
    data = {
        "repo_backend": "neo4j",
        "neo4j_uri": "bolt://db:7687",
        "neo4j_user": "neo4j",
        "neo4j_password": "pw",
        "queue_backend": "kafka",
        "kafka_bootstrap": "localhost:9092",
    }
    cfg_file = tmp_path / "dm.yml"
    cfg_file.write_text(yaml.safe_dump(data))
    cfg = load_dagmanager_config(str(cfg_file))
    assert cfg.neo4j_uri == data["neo4j_uri"]
    assert cfg.kafka_bootstrap == data["kafka_bootstrap"]


def test_load_dagmanager_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_dagmanager_config("nope.yml")


def test_load_dagmanager_config_malformed(tmp_path: Path):
    f = tmp_path / "bad.yml"
    f.write_text("- 1")
    with pytest.raises(TypeError):
        load_dagmanager_config(str(f))

