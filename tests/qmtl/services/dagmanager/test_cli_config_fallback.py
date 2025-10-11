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
