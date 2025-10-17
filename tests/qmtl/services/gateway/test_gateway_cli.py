import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["service", "--help"], "usage: qmtl service"),
        (["service", "gateway", "--help"], "usage: qmtl service gateway"),
        (["service", "dagmanager", "--help"], "usage: qmtl service dagmanager"),
        (["service", "dagmanager", "server", "--help"], "usage: qmtl service dagmanager server"),
        (["service", "dagmanager", "metrics", "--help"], "usage: qmtl service dagmanager metrics"),
        (["tools", "--help"], "usage: qmtl tools"),
        (["tools", "sdk", "--help"], "usage: qmtl tools sdk"),
        (["project", "--help"], "usage: qmtl project"),
        (["project", "init", "--help"], "usage: qmtl project init"),
    ],
)
def test_cli_subcommand_help(args, expected):
    result = subprocess.run([sys.executable, "-m", "qmtl", *args], capture_output=True, text=True)
    assert result.returncode == 0
    assert expected in result.stdout


@pytest.mark.parametrize(
    "cmd",
    [
        "gw",
        "gateway",
        "dagmanager",
        "dagmanager-server",
        "dagmanager-metrics",
        "sdk",
        "taglint",
        "report",
        "init",
    ],
)
def test_removed_top_level_aliases_show_top_level_usage(cmd):
    result = subprocess.run(
        [sys.executable, "-m", "qmtl", cmd, "--help"], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert result.stdout
    assert result.stdout.splitlines()[0].startswith("usage: qmtl")
    assert "error: unknown command" in result.stderr
    assert cmd in result.stderr


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
                "dagmanager:",
                "  enable_topic_namespace: false",
            ]
        )
    )

    captured = {}

    from types import SimpleNamespace
    from qmtl.services.gateway import cli

    namespace_calls: list[bool] = []

    def fake_set_namespace(enabled: bool) -> None:
        namespace_calls.append(enabled)

    class DummyDB:
        async def connect(self):
            captured["connect"] = True

        async def close(self):
            captured["close"] = True

    def fake_create_app(**kwargs):
        captured["db_backend"] = kwargs.get("database_backend")
        captured["db_dsn"] = kwargs.get("database_dsn")
        captured["redis"] = isinstance(kwargs.get("redis_client"), cli.InMemoryRedis)
        captured["insert_sentinel"] = kwargs.get("insert_sentinel")
        return SimpleNamespace(state=SimpleNamespace(database=DummyDB()))

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr(cli, "set_topic_namespace_enabled", fake_set_namespace)

    fake_uvicorn = SimpleNamespace(run=lambda app, host, port: captured.update({"host": host, "port": port}))
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.chdir(tmp_path)

    cli.main([])

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 12345
    assert captured["db_backend"] == "memory"
    assert captured["db_dsn"] == "sqlite:///:memory:"
    assert captured["redis"]
    assert captured["insert_sentinel"] is True
    assert namespace_calls == [False]


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
    from qmtl.services.gateway import cli

    class DummyRedis:
        pass

    def fake_from_url(dsn, decode_responses=True):
        captured["dsn"] = dsn
        captured["decode"] = decode_responses
        return DummyRedis()

    def fake_create_app(**kwargs):
        captured["redis"] = kwargs.get("redis_client")
        captured["insert_sentinel"] = kwargs.get("insert_sentinel")
        return SimpleNamespace(state=SimpleNamespace(database=None))

    monkeypatch.setattr(cli.redis, "from_url", fake_from_url)
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **k: None))
    monkeypatch.chdir(tmp_path)

    cli.main([])

    assert isinstance(captured["redis"], DummyRedis)
    assert captured["dsn"] == "redis://x:6379"
    assert captured["decode"] is True
    assert captured["insert_sentinel"] is True


def test_gateway_cli_no_sentinel_flag(monkeypatch, tmp_path):
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: 127.0.0.1",
                "  port: 12345",
                "  insert_sentinel: true",
            ]
        )
    )

    captured = {}

    from types import SimpleNamespace
    from qmtl.services.gateway import cli

    def fake_create_app(**kwargs):
        captured["insert_sentinel"] = kwargs.get("insert_sentinel")
        return SimpleNamespace(state=SimpleNamespace(database=None))

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **k: None))
    monkeypatch.chdir(tmp_path)

    cli.main(["--no-sentinel"])

    assert captured["insert_sentinel"] is False


def test_gateway_cli_allow_live_flag(monkeypatch, tmp_path):
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        "\n".join(
            [
                "gateway:",
                "  host: 127.0.0.1",
                "  port: 12345",
                "  enforce_live_guard: true",
            ]
        )
    )

    captured = {}

    from types import SimpleNamespace
    from qmtl.services.gateway import cli

    def fake_create_app(**kwargs):
        captured["enforce_live_guard"] = kwargs.get("enforce_live_guard")
        return SimpleNamespace(state=SimpleNamespace(database=None))

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **k: None))
    monkeypatch.chdir(tmp_path)

    cli.main(["--allow-live"])

    assert captured["enforce_live_guard"] is False


def test_gateway_cli_db_connect_failure(monkeypatch, tmp_path):
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

    from types import SimpleNamespace
    from qmtl.services.gateway import cli

    class DummyDB:
        async def connect(self):
            raise RuntimeError("boom")

        async def close(self):
            pass

    def fake_create_app(**kwargs):
        return SimpleNamespace(state=SimpleNamespace(database=DummyDB()))

    logged = {}

    def fake_exception(msg):
        logged["msg"] = msg

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **k: None))
    monkeypatch.setattr(cli.logging, "exception", fake_exception)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        cli.main([])

    assert logged["msg"] == "Failed to connect to database"


def test_gateway_cli_db_close_failure(monkeypatch, tmp_path):
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

    from types import SimpleNamespace
    from qmtl.services.gateway import cli

    class DummyDB:
        async def connect(self):
            pass

        async def close(self):
            raise RuntimeError("boom")

    def fake_create_app(**kwargs):
        return SimpleNamespace(state=SimpleNamespace(database=DummyDB()))

    logged = {}

    def fake_exception(msg):
        logged["msg"] = msg

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=lambda *a, **k: None))
    monkeypatch.setattr(cli.logging, "exception", fake_exception)
    monkeypatch.chdir(tmp_path)

    cli.main([])

    assert logged["msg"] == "Failed to close database connection"

