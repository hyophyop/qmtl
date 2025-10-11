import logging
import sys
from types import SimpleNamespace

import pytest

from qmtl.services.gateway import cli


@pytest.fixture
def gateway_testbed(monkeypatch):
    captured: dict[str, object] = {}

    class DummyDB:
        async def connect(self):
            captured["connected"] = True

        async def close(self):
            captured["closed"] = True

    def fake_create_app(**kwargs):
        captured["app_kwargs"] = kwargs
        return SimpleNamespace(state=SimpleNamespace(database=DummyDB()))

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(
            run=lambda app, host, port: captured.update({"uvicorn": {"host": host, "port": port}})
        ),
    )
    return captured


def test_gateway_cli_prefers_env_path(tmp_path, monkeypatch, caplog, gateway_testbed):
    config_path = tmp_path / "external.yml"
    config_path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: 127.0.0.1",
                "  port: 12345",
                "  database_backend: memory",
                "  database_dsn: 'sqlite:///:memory:'",
            ]
        )
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.chdir(run_dir)
    monkeypatch.setenv("QMTL_CONFIG_FILE", str(config_path))

    caplog.set_level(logging.INFO)
    cli.main([])

    assert gateway_testbed["uvicorn"] == {"host": "127.0.0.1", "port": 12345}
    assert gateway_testbed["app_kwargs"]["database_backend"] == "memory"
    assert any(
        "QMTL_CONFIG_FILE" in record.message and "loaded" in record.message
        for record in caplog.records
    )


def test_gateway_cli_invalid_env_path_warns_and_falls_back(
    tmp_path, monkeypatch, caplog, gateway_testbed
):
    env_path = tmp_path / "missing.yml"
    run_dir = tmp_path / "cwd"
    run_dir.mkdir()
    fallback = run_dir / "qmtl.yml"
    fallback.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: 10.0.0.5",
                "  port: 2222",
                "  database_backend: memory",
                "  database_dsn: 'sqlite:///:memory:'",
            ]
        )
    )

    monkeypatch.chdir(run_dir)
    monkeypatch.setenv("QMTL_CONFIG_FILE", str(env_path))

    caplog.set_level(logging.WARNING)
    cli.main([])

    assert gateway_testbed["uvicorn"] == {"host": "10.0.0.5", "port": 2222}
    assert any("QMTL_CONFIG_FILE" in record.message and "ignored" in record.message for record in caplog.records)


def test_gateway_cli_errors_when_section_missing(tmp_path, monkeypatch, caplog, gateway_testbed):
    config_path = tmp_path / "no_gateway.yml"
    config_path.write_text("dagmanager:\n  grpc_port: 1234\n")

    caplog.set_level(logging.ERROR)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--config", str(config_path)])

    assert exc.value.code == 2
    assert any(
        "does not define the 'gateway' section" in record.message for record in caplog.records
    )
