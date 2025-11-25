import logging
from pathlib import Path

import pytest

from qmtl.services.dagmanager.config import DagManagerConfig, load_dagmanager_config


def test_load_config_maps_aliases(tmp_path: Path):
    config_path = tmp_path / "dag.yml"
    config_path.write_text(
        """
neo4j_dsn: bolt://neo4j.local
kafka_dsn: kafka://broker.local
controlbus_dsn: kafka://controlbus.local
memory_repo_path: repo.gpickle
grpc_port: 1234
""".strip()
    )

    cfg = load_dagmanager_config(str(config_path))

    assert cfg == DagManagerConfig(
        neo4j_dsn="bolt://neo4j.local",
        kafka_dsn="kafka://broker.local",
        controlbus_dsn="kafka://controlbus.local",
        memory_repo_path="repo.gpickle",
        grpc_port=1234,
    )


def test_load_config_raises_on_invalid_yaml(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    config_path = tmp_path / "invalid.yml"
    config_path.write_text("grpc_port: [oops\n")

    caplog.set_level(logging.ERROR)
    with pytest.raises(ValueError):
        load_dagmanager_config(str(config_path))

    assert any("Failed to parse configuration file" in rec.message for rec in caplog.records)


def test_load_config_validates_mapping(tmp_path: Path):
    config_path = tmp_path / "invalid_type.yml"
    config_path.write_text("- not_a_mapping")

    with pytest.raises(TypeError):
        load_dagmanager_config(str(config_path))


def test_load_config_propagates_missing_file(tmp_path: Path):
    missing_path = tmp_path / "missing.yml"

    with pytest.raises(FileNotFoundError):
        load_dagmanager_config(str(missing_path))


def test_load_config_preserves_canonical_over_alias(tmp_path: Path):
    config_path = tmp_path / "prefer_canonical.yml"
    config_path.write_text(
        """
neo4j_dsn: bolt://primary
grpc_port: 5555
""".strip()
    )

    cfg = load_dagmanager_config(str(config_path))

    assert cfg.neo4j_dsn == "bolt://primary"
    assert cfg.grpc_port == 5555


def test_load_config_rejects_aliases(tmp_path: Path):
    config_path = tmp_path / "alias.yml"
    config_path.write_text(
        """
neo4j_url: bolt://alias
kafka_url: kafka://broker
""".strip()
    )

    with pytest.raises(TypeError):
        load_dagmanager_config(str(config_path))
