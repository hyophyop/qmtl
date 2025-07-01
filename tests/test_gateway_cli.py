import subprocess
import sys


def test_gateway_cli_help():
    result = subprocess.run([sys.executable, "-m", "qmtl", "gw", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--config" in result.stdout


def test_gateway_cli_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "cfg.yml"
    config_path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: 127.0.0.1",
                "  port: 12345",
                "  offline: true",
                "  database_backend: memory",
                "  database_dsn: 'sqlite:///:memory:'",
            ]
        )
    )

    captured = {}

    from types import SimpleNamespace
    from qmtl.gateway import cli

    class DummyDB:
        async def connect(self):
            captured["connect"] = True

        async def close(self):
            captured["close"] = True

    def fake_create_app(**kwargs):
        captured["db_backend"] = kwargs.get("database_backend")
        captured["db_dsn"] = kwargs.get("database_dsn")
        captured["redis"] = isinstance(kwargs.get("redis_client"), cli.InMemoryRedis)
        return SimpleNamespace(state=SimpleNamespace(database=DummyDB()))

    monkeypatch.setattr(cli, "create_app", fake_create_app)

    fake_uvicorn = SimpleNamespace(run=lambda app, host, port: captured.update({"host": host, "port": port}))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)

    cli.main(["--config", str(config_path)])

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 12345
    assert captured["db_backend"] == "memory"
    assert captured["db_dsn"] == "sqlite:///:memory:"
    assert captured["redis"]

