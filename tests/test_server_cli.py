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

    async def fake_run(cfg):
        captured["repo"] = cfg.repo_backend
        captured["queue"] = cfg.queue_backend

    monkeypatch.setattr("qmtl.dagmanager.server._run", fake_run)
    main([])
    assert captured["repo"] == "neo4j"
    assert captured["queue"] == "kafka"


def test_server_config_file(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.yml"
    cfg.write_text(yaml.safe_dump({"dagmanager": {"neo4j_uri": "bolt://test:7687"}}))

    captured = {}

    async def fake_run(cfg):
        captured["uri"] = cfg.neo4j_uri

    monkeypatch.setattr("qmtl.dagmanager.server._run", fake_run)
    main(["--config", str(cfg)])
    assert captured["uri"] == "bolt://test:7687"
