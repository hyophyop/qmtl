from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from qmtl.interfaces.cli import config as cli_config


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    content = {
        "gateway": {
            "redis_dsn": "redis://localhost:6379/0",
            "database_backend": "sqlite",
            "database_dsn": str(tmp_path / "gateway.db"),
            "controlbus_brokers": ["localhost:9092"],
            "controlbus_topics": ["events"],
            "worldservice_url": "http://localhost:8080",
        },
        "dagmanager": {
            "kafka_dsn": "localhost:9092",
            "controlbus_dsn": "localhost:9092",
            "controlbus_queue_topic": "queue",
        },
    }
    path = tmp_path / "qmtl.yml"
    path.write_text(yaml.safe_dump(content))
    return path


@pytest.fixture
def mock_validation_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyRedis:
        async def ping(self) -> bool:  # pragma: no cover - simple stub
            return True

        async def close(self) -> None:  # pragma: no cover - simple stub
            return None

    monkeypatch.setattr(
        "qmtl.foundation.config_validation.redis.from_url",
        lambda dsn: DummyRedis(),
    )

    class DummyResponse:
        status_code = 200
        content = b"{}"

        def json(self) -> dict:
            return {}

    class DummyClient:
        async def __aenter__(self) -> "DummyClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, timeout: float):
            return DummyResponse()

    monkeypatch.setattr(
        "qmtl.foundation.config_validation.httpx.AsyncClient",
        lambda: DummyClient(),
    )

    async def fake_ready(self):
        return True

    monkeypatch.setattr(
        "qmtl.foundation.config_validation.ControlBusConsumer._broker_ready",
        fake_ready,
    )

    class DummyKafkaAdmin:
        def __init__(self) -> None:
            self.client = self

        def list_topics(self):  # pragma: no cover - simple stub
            return {"topic": {}}

    async def fake_admin(dsn: str):
        return DummyKafkaAdmin()

    monkeypatch.setattr(
        "qmtl.foundation.config_validation._create_kafka_admin",
        fake_admin,
    )


def test_validate_success_outputs_table(
    config_file: Path, mock_validation_deps: None, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_config.run(["validate", "--config", str(config_file)])
    captured = capsys.readouterr()
    assert "gateway:" in captured.out
    assert "redis" in captured.out
    assert "OK" in captured.out
    assert "dagmanager:" in captured.out
    assert "Kafka reachable" in captured.out


def test_validate_failure_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    content = {
        "gateway": {
            "database_backend": "postgres",
            "database_dsn": "postgresql://example.invalid/db",
            "enable_worldservice_proxy": False,
        },
        "dagmanager": {},
    }
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(yaml.safe_dump(content))

    async def fail_connect(dsn: str):
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr("qmtl.foundation.config_validation.asyncpg.connect", fail_connect)

    with pytest.raises(SystemExit) as excinfo:
        cli_config.run(["validate", "--config", str(cfg), "--target", "gateway"])

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "database" in captured.out
    assert "ERROR" in captured.out


def test_validate_offline_skips_checks(
    config_file: Path, mock_validation_deps: None, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_config.run(["validate", "--config", str(config_file), "--offline"])
    captured = capsys.readouterr()
    assert "Offline mode" in captured.out
    assert "skipped Kafka admin" in captured.out


def test_validate_json_output(
    config_file: Path, mock_validation_deps: None, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_config.run(
        [
            "validate",
            "--config",
            str(config_file),
            "--target",
            "gateway",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out[captured.out.index("{") :])
    assert payload["status"] == "ok"
    assert payload["results"]["gateway"]["redis"]["severity"] == "ok"


def test_validate_missing_config_path(capsys: pytest.CaptureFixture[str]) -> None:
    missing = Path("/nonexistent/qmtl.yml")
    with pytest.raises(SystemExit) as excinfo:
        cli_config.run(["validate", "--config", str(missing)])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "does not exist" in captured.err
