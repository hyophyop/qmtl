"""Tests for QMTL v2.0 CLI."""

from __future__ import annotations

from qmtl.interfaces.cli.submit import cmd_submit
from qmtl.interfaces.cli.v2 import COMMANDS, LEGACY_COMMANDS, ADMIN_COMMANDS, main
from qmtl.runtime.sdk.configuration import reset_runtime_config_cache


class TestCLIHelp:
    """Tests for CLI help output."""

    def test_help_with_no_args(self, capsys):
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "QMTL v2.0" in captured.out
        assert "submit" in captured.out

    def test_help_with_h_flag(self, capsys):
        result = main(["-h"])
        assert result == 0
        captured = capsys.readouterr()
        assert "submit" in captured.out

    def test_help_with_help_flag(self, capsys):
        result = main(["--help"])
        assert result == 0


class TestCLIVersion:
    """Tests for version command."""

    def test_version(self, capsys):
        result = main(["version"])
        assert result == 0
        captured = capsys.readouterr()
        assert "QMTL version" in captured.out


class TestCLIStatus:
    """Tests for status command."""

    def test_status_lists_strategies_when_no_args(self, capsys, monkeypatch):
        class DummyResp:
            status_code = 200
            def json(self):
                return []
        class DummyClient:
            def __init__(self, timeout):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def get(self, url, params=None):
                return DummyResp()
        monkeypatch.setattr("httpx.Client", DummyClient)

        result = main(["status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "No strategies" in captured.out

    def test_status_fetches_strategy(self, monkeypatch, capsys):
        class DummyResp:
            status_code = 200
            def json(self):
                return {"status": "active"}
        class DummyClient:
            def __init__(self, timeout):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def get(self, url, params=None):
                return DummyResp()
        monkeypatch.setattr("httpx.Client", DummyClient)

        result = main(["status", "--strategy", "s-1"])
        assert result == 0
        captured = capsys.readouterr()
        assert "s-1" in captured.out
        assert "active" in captured.out

    def test_status_lists_strategies(self, monkeypatch, capsys):
        class DummyResp:
            status_code = 200
            def json(self):
                return [{"id": "s1", "status": "active", "world": "w1", "mode": "live"}]
        class DummyClient:
            def __init__(self, timeout):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def get(self, url, params=None):
                return DummyResp()
        monkeypatch.setattr("httpx.Client", DummyClient)

        result = main(["status"])
        assert result == 0
        captured = capsys.readouterr()
        assert "s1" in captured.out
        assert "w1" in captured.out


class TestCLIWorld:
    """Tests for world command."""

    def test_world_list(self, monkeypatch, capsys):
        class DummyResp:
            status_code = 200
            def json(self):
                return [{"id": "w1", "name": "World 1"}]
        class DummyClient:
            def __init__(self, timeout):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def get(self, url, params=None):
                return DummyResp()
        monkeypatch.setattr("httpx.Client", DummyClient)

        result = main(["world", "list"])
        assert result == 0
        captured = capsys.readouterr()
        assert "w1" in captured.out

    def test_world_create_no_name(self, capsys):
        result = main(["world", "create"])
        assert result == 1
        captured = capsys.readouterr()
        assert "World name required" in captured.err

    def test_world_create_success(self, monkeypatch, capsys):
        class DummyResp:
            status_code = 201
            def json(self):
                return {"id": "w2"}
        class DummyClient:
            def __init__(self, timeout):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def post(self, url, json):
                return DummyResp()
        monkeypatch.setattr("httpx.Client", DummyClient)

        result = main(["world", "create", "w2"])
        assert result == 0
        captured = capsys.readouterr()
        assert "w2" in captured.out


class TestCLIInit:
    """Tests for init command."""

    def test_init_creates_project(self, tmp_path, capsys):
        project_dir = tmp_path / "test_project"
        result = main(["init", str(project_dir)])
        assert result == 0

        # Check files were created
        assert (project_dir / "qmtl.yml").exists()
        assert (project_dir / "strategies" / "__init__.py").exists()
        assert (project_dir / "strategies" / "my_strategy.py").exists()
        assert (project_dir / ".env.example").exists()

        captured = capsys.readouterr()
        assert "Project initialized" in captured.out
        assert "Next steps:" in captured.out

    def test_init_non_empty_dir(self, tmp_path, capsys):
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        (project_dir / "existing_file.txt").touch()
        
        result = main(["init", str(project_dir)])
        assert result == 1
        captured = capsys.readouterr()
        assert "not empty" in captured.err


class TestSubmitStrategyRoot:
    """Strategy resolution driven by qmtl.yml project section."""

    def test_submit_uses_project_strategy_root_and_default_world(
        self, tmp_path, monkeypatch
    ):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        config = workspace / "qmtl.yml"
        config.write_text(
            """
project:
  strategy_root: strategies
  default_world: demo_world
"""
        )

        strategies = workspace / "strategies"
        strategies.mkdir()
        (strategies / "__init__.py").write_text("")
        (strategies / "demo.py").write_text(
            """
from qmtl.runtime.sdk import Strategy


class DemoStrategy(Strategy):
    def setup(self):
        pass
"""
        )

        monkeypatch.chdir(workspace)
        monkeypatch.setenv("QMTL_DEFAULT_WORLD", "override_world")
        reset_runtime_config_cache()

        captured: dict[str, object] = {}

        def fake_submit(strategy_cls, args, overrides):
            captured["strategy"] = strategy_cls
            captured["world"] = args.world
            return 0

        monkeypatch.setattr(
            "qmtl.interfaces.cli.submit._submit_and_print_result", fake_submit
        )

        result = cmd_submit(["strategies.demo:DemoStrategy"])

        assert result == 0
        assert captured["world"] == "demo_world"
        assert getattr(captured["strategy"], "__name__") == "DemoStrategy"
        reset_runtime_config_cache()

    def test_submit_falls_back_to_env_default_world(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace_env"
        workspace.mkdir()

        strategies = workspace / "strategies"
        strategies.mkdir()
        (strategies / "__init__.py").write_text("")
        (strategies / "demo.py").write_text(
            """
from qmtl.runtime.sdk import Strategy


class DemoStrategy(Strategy):
    def setup(self):
        pass
"""
        )

        monkeypatch.chdir(workspace)
        monkeypatch.setenv("QMTL_DEFAULT_WORLD", "env_world")
        reset_runtime_config_cache()

        captured: dict[str, object] = {}

        def fake_submit(strategy_cls, args, overrides):
            captured["world"] = args.world
            return 0

        monkeypatch.setattr(
            "qmtl.interfaces.cli.submit._submit_and_print_result", fake_submit
        )

        result = cmd_submit(["strategies.demo:DemoStrategy"])

        assert result == 0
        assert captured["world"] == "env_world"
        reset_runtime_config_cache()


class TestCLILegacyCommands:
    """Tests for legacy command handling."""

    def test_legacy_service_command(self, capsys):
        result = main(["service"])
        assert result == 2
        captured = capsys.readouterr()
        assert "has been removed" in captured.err
        assert "qmtl submit" in captured.err

    def test_legacy_tools_command(self, capsys):
        result = main(["tools"])
        assert result == 2
        captured = capsys.readouterr()
        assert "has been removed" in captured.err

    def test_legacy_project_command(self, capsys):
        result = main(["project"])
        assert result == 2
        captured = capsys.readouterr()
        assert "has been removed" in captured.err
        assert "qmtl init" in captured.err


class TestCLIUnknownCommand:
    """Tests for unknown command handling."""

    def test_unknown_command(self, capsys):
        result = main(["unknown_cmd"])
        assert result == 2
        captured = capsys.readouterr()
        assert "Unknown command" in captured.err


class TestCommandRegistry:
    """Tests for command registry."""

    def test_all_commands_registered(self):
        expected = {"submit", "status", "world", "init", "version"}
        assert set(COMMANDS.keys()) == expected

    def test_legacy_commands_documented(self):
        # Legacy commands that show deprecation warnings
        expected = {"service", "tools", "project", "config", "run", "offline"}
        assert set(LEGACY_COMMANDS.keys()) == expected
    
    def test_admin_commands_registered(self):
        """Admin commands are available but not shown in main help."""
        expected = {"gw", "gateway", "dagmanager-server", "taglint"}
        assert set(ADMIN_COMMANDS.keys()) == expected
