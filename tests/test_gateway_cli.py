import subprocess
import sys
import pytest


@pytest.mark.parametrize("cmd", ["gw", "dagm", "dagmgr-server", "sdk"])
def test_cli_subcommand_help(cmd):
    result = subprocess.run([sys.executable, "-m", "qmtl", cmd, "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert f"usage: qmtl {cmd}" in result.stdout


def test_gateway_cli_config_file(monkeypatch, tmp_path):
    config_path = tmp_path / "qmtl.yml"
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
    monkeypatch.chdir(tmp_path)

    cli.main([])

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 12345
    assert captured["db_backend"] == "memory"
    assert captured["db_dsn"] == "sqlite:///:memory:"
    assert captured["redis"]


def test_gateway_cli_redis_backend(monkeypatch, tmp_path):
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: 127.0.0.1",
                "  port: 12345",
                "  redis_dsn: redis://x:6379",
                "  database_backend: memory",
                "  database_dsn: 'sqlite:///:memory:'",
            ]
        )
    )

    captured = {}

    from types import SimpleNamespace
    from qmtl.gateway import cli

    class DummyRedis:
        pass

    def fake_from_url(dsn, decode_responses=True):
        captured["dsn"] = dsn
        captured["decode"] = decode_responses
        return DummyRedis()

    def fake_create_app(**kwargs):
        captured["redis"] = kwargs.get("redis_client")
        return SimpleNamespace(state=SimpleNamespace(database=None))

    monkeypatch.setattr(cli.redis, "from_url", fake_from_url)
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **k: None))
    monkeypatch.chdir(tmp_path)

    cli.main([])

    assert isinstance(captured["redis"], DummyRedis)
    assert captured["dsn"] == "redis://x:6379"
    assert captured["decode"] is True

