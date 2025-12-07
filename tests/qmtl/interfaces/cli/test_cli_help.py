"""CLI help tests for the v2 command surface."""

import subprocess
import sys

def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "qmtl", *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _output(result: subprocess.CompletedProcess[str]) -> str:
    """Return stdout if present, otherwise stderr."""
    return result.stdout or result.stderr


def test_dagmanager_help_shows_subcommands() -> None:
    result = _run_cli("dagmanager-server", "--help")
    assert result.returncode == 0
    text = _output(result)
    assert "Operate DAG Manager" in text or "dagmanager" in text
    assert "diff" in text or "server" in text


def test_gateway_help_shows_flags() -> None:
    result = _run_cli("gw", "--help")
    assert result.returncode == 0
    text = _output(result)
    assert "Gateway" in text
    assert "--config" in text or "Run the Gateway HTTP server" in text


def test_submit_help_shows_usage() -> None:
    result = _run_cli("submit", "--help")
    assert result.returncode == 0
    text = _output(result).lower()
    assert "strategy" in text or "usage" in text


def test_v2_world_help() -> None:
    """Test v2 world command shows subcommands."""
    result = _run_cli("world", "--help")
    assert result.returncode == 0
    text = _output(result)
    assert "list" in text or "create" in text
