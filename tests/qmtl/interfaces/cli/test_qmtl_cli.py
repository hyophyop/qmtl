"""QMTL CLI main entry point tests.

Note: As of v2.0, the CLI structure has been simplified.
Legacy 4-level commands replaced with flat v2 commands.
"""

import subprocess
import sys

import pytest


def test_qmtl_help():
    """Test v2 CLI shows new simplified commands."""
    result = subprocess.run([sys.executable, "-m", "qmtl", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    
    # v2 commands should be present
    for subcommand in ("submit", "status", "world", "init"):
        assert subcommand in result.stdout, f"Expected '{subcommand}' in v2 CLI help"

    # Legacy shortcuts (gw, dagmanager-server) are still supported for convenience
    # but main commands are v2 style


@pytest.mark.skip(reason="Legacy CLI structure removed in v2.0")
def test_qmtl_legacy_help():
    """Legacy test - old 4-level CLI structure."""
    result = subprocess.run([sys.executable, "-m", "qmtl", "--help"], capture_output=True, text=True)
    for subcommand in ("config", "project", "service", "tools"):
        assert subcommand in result.stdout
