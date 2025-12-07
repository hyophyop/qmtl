"""QMTL CLI v2 entry point tests."""

import subprocess
import sys


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "qmtl", *args], capture_output=True, text=True)


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout or result.stderr


def test_qmtl_help():
    """Test v2 CLI shows new simplified commands."""
    result = _run_cli("--help")
    assert result.returncode == 0

    # v2 commands should be present
    for subcommand in ("submit", "status", "world", "init"):
        assert subcommand in _output(result), f"Expected '{subcommand}' in v2 CLI help"


def test_qmtl_admin_help_lists_operator_commands():
    """Admin help should expose operator commands without legacy v1 tree."""
    result = _run_cli("--help-admin")
    assert result.returncode == 0
    text = _output(result)
    for cmd in ("gw", "gateway", "dagmanager-server", "taglint"):
        assert cmd in text
