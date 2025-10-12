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


def test_dagmanager_cli_honors_cli_path(tmp_path, monkeypatch, caplog, dagmanager_testbed):
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

    caplog.set_level(logging.INFO)
    server.main(["--config", str(config_path)])

    cfg = dagmanager_testbed["config"]
    assert cfg.grpc_port == 60000
    assert cfg.http_port == 61000
    assert any(
        "DAG Manager configuration loaded from" in record.message and "--config" in record.message
        for record in caplog.records
    )


def test_dagmanager_cli_discovers_default_file(tmp_path, monkeypatch, caplog, dagmanager_testbed):
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

    caplog.set_level(logging.INFO)
    server.main([])

    cfg = dagmanager_testbed["config"]
    assert cfg.grpc_port == 61001
    assert cfg.http_port == 62001
    assert any(
        "DAG Manager configuration loaded from" in record.message and str(fallback) in record.message
        for record in caplog.records
    )


def test_dagmanager_cli_errors_when_section_missing(tmp_path, monkeypatch, caplog, dagmanager_testbed):
    config_path = tmp_path / "no_dagmanager.yml"
    config_path.write_text("gateway:\n  host: example\n")

    caplog.set_level(logging.ERROR)
    with pytest.raises(SystemExit) as exc:
        server.main(["--config", str(config_path)])

    assert exc.value.code == 2
    assert any(
        "does not define the 'dagmanager' section" in record.message for record in caplog.records
    )
