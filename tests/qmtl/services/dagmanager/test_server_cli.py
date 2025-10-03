import pytest
import pytest
import yaml

from qmtl.services.dagmanager.server import main


def test_server_help(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "qmtl service dagmanager server" in out
    assert "--config" in out


def test_server_defaults(monkeypatch, tmp_path):
    captured = {}

    async def fake_run(config):
        captured["neo4j"] = config.neo4j_dsn
        captured["kafka"] = config.kafka_dsn

    monkeypatch.setattr("qmtl.services.dagmanager.server._run", fake_run)
    monkeypatch.chdir(tmp_path)
    main([])
    assert captured["neo4j"] is None
    assert captured["kafka"] is None


def test_server_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        yaml.safe_dump({"dagmanager": {"neo4j_dsn": "bolt://test:7687"}})
    )

    captured = {}

    async def fake_run(config):
        captured["uri"] = config.neo4j_dsn

    monkeypatch.setattr("qmtl.services.dagmanager.server._run", fake_run)
    monkeypatch.chdir(tmp_path)
    main([])
    assert captured["uri"] == "bolt://test:7687"
