import pytest
import yaml
from qmtl.dagmanager.server import main


def test_server_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "qmtl dagmgr-server" in out
    assert "--config" in out


def test_server_defaults(monkeypatch):
    captured = {}

    async def fake_run(config):
        captured["repo"] = config.repo_backend
        captured["queue"] = config.queue_backend

    monkeypatch.setattr("qmtl.dagmanager.server._run", fake_run)
    main([])
    assert captured["repo"] == "memory"
    assert captured["queue"] == "memory"


def test_server_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "cfg.yml"
    config_path.write_text(
        yaml.safe_dump({"dagmanager": {"neo4j_dsn": "bolt://test:7687"}})
    )

    captured = {}

    async def fake_run(config):
        captured["uri"] = config.neo4j_dsn

    monkeypatch.setattr("qmtl.dagmanager.server._run", fake_run)
    main(["--config", str(config_path)])
    assert captured["uri"] == "bolt://test:7687"
