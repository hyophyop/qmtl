import pytest
from qmtl.dagmanager.server import main


def test_server_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "qmtl-dagmgr-server" in capsys.readouterr().out


def test_server_defaults(monkeypatch):
    captured = {}

    async def fake_run(args):
        captured["repo"] = args.repo_backend
        captured["queue"] = args.queue_backend

    monkeypatch.setattr("qmtl.dagmanager.server._run", fake_run)
    main([])
    assert captured["repo"] == "neo4j"
    assert captured["queue"] == "kafka"


def test_server_config_file(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.yml"
    cfg.write_text("neo4j_uri: bolt://test:7687\n")

    captured = {}

    async def fake_run(args):
        captured["uri"] = args.neo4j_uri

    monkeypatch.setattr("qmtl.dagmanager.server._run", fake_run)
    main(["--config", str(cfg)])
    assert captured["uri"] == "bolt://test:7687"
