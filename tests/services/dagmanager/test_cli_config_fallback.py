import json
import logging

import pytest

from qmtl.services.dagmanager import server


@pytest.fixture
def dagmanager_testbed(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run(cfg):
        captured["config"] = cfg

    monkeypatch.setattr(server, "_run", fake_run)
    return captured


def test_dagmanager_cli_prefers_env_path(tmp_path, monkeypatch, caplog, dagmanager_testbed):
    config_path = tmp_path / "external.yml"
    config_path.write_text(
        "\n".join(
            [
                "dagmanager:",
                "  grpc_port: 60000",
                "  http_port: 61000",
            ]
        )
    )

    workdir = tmp_path / "run"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("QMTL_CONFIG_FILE", str(config_path))

    caplog.set_level(logging.INFO)
    server.main([])

    cfg = dagmanager_testbed["config"]
    assert cfg.grpc_port == 60000
    assert cfg.http_port == 61000
    assert any(
        "QMTL_CONFIG_FILE" in record.message and "loaded" in record.message
        for record in caplog.records
    )


def test_dagmanager_cli_invalid_env_path_warns_and_falls_back(
    tmp_path, monkeypatch, caplog, dagmanager_testbed
):
    bad_path = tmp_path / "missing.yml"
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    fallback = workdir / "qmtl.yaml"
    fallback.write_text(
        "\n".join(
            [
                "dagmanager:",
                "  grpc_port: 61001",
                "  http_port: 62001",
            ]
        )
    )

    monkeypatch.chdir(workdir)
    monkeypatch.setenv("QMTL_CONFIG_FILE", str(bad_path))

    caplog.set_level(logging.WARNING)
    server.main([])

    cfg = dagmanager_testbed["config"]
    assert cfg.grpc_port == 61001
    assert cfg.http_port == 62001
    assert any("QMTL_CONFIG_FILE" in record.message and "ignored" in record.message for record in caplog.records)


def test_dagmanager_cli_warns_when_section_missing_with_metadata(
    tmp_path, monkeypatch, caplog, dagmanager_testbed
):
    config_path = tmp_path / "no_dagmanager.yml"
    config_path.write_text("gateway:\n  host: example\n")

    monkeypatch.setenv(
        "QMTL_CONFIG_EXPORT",
        json.dumps({"generated_at": "2024-03-10T00:00:00Z", "variables": 2}),
    )
    monkeypatch.setenv("QMTL_CONFIG_SOURCE", str(config_path))

    caplog.set_level(logging.WARNING)
    server.main(["--config", str(config_path)])

    cfg = dagmanager_testbed["config"]
    assert cfg.grpc_port == 50051
    assert cfg.http_port == 8001
    assert any(
        "does not define the 'dagmanager' section" in record.message and "QMTL_CONFIG_EXPORT" in record.message
        for record in caplog.records
    )
