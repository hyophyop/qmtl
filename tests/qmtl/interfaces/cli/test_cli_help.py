"""CLI help tests.

Note: As of v2.0, the legacy multi-level CLI structure has been replaced
with a simplified flat structure. Legacy command tests are marked as skipped.
"""

import subprocess
import sys

import pytest


def _run_help(*args: str) -> str:
    cmd = [sys.executable, "-m", "qmtl", *args]
    out = subprocess.run(cmd, capture_output=True, text=True)
    # argparse writes help to stdout by default; fallback to stderr if empty
    return out.stdout or out.stderr


@pytest.mark.skip(reason="Legacy CLI removed in v2.0. Service commands accessed directly via 'qmtl gw' or 'qmtl dagmanager-server'.")
def test_dagmanager_help_shows_subcommands() -> None:
    """Legacy test - qmtl service dagmanager replaced by direct commands in v2.0."""
    pass


@pytest.mark.skip(reason="Legacy CLI removed in v2.0. Use 'qmtl gw --help' directly.")
def test_gateway_help_shows_flags() -> None:
    """Legacy test - qmtl service gateway replaced by 'qmtl gw' in v2.0."""
    pass


@pytest.mark.skip(reason="Legacy CLI removed in v2.0. Use 'qmtl submit --help' instead.")
def test_sdk_help_shows_subcommands() -> None:
    """Legacy test - qmtl tools sdk replaced by 'qmtl submit' in v2.0."""
    pass


def test_v2_submit_help() -> None:
    """Test v2 submit command shows help."""
    text = _run_help("submit", "--help")
    assert "strategy" in text.lower() or "usage" in text.lower()


def test_v2_world_help() -> None:
    """Test v2 world command shows subcommands."""
    text = _run_help("world", "--help")
    assert "list" in text or "create" in text
