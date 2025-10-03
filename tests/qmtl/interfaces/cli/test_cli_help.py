from __future__ import annotations

import subprocess
import sys


def _run_help(*args: str) -> str:
    cmd = [sys.executable, "-m", "qmtl", *args]
    out = subprocess.run(cmd, capture_output=True, text=True)
    # argparse writes help to stdout by default; fallback to stderr if empty
    return out.stdout or out.stderr


def test_dagmanager_help_shows_subcommands() -> None:
    text = _run_help("dagmanager", "--help")
    assert "diff" in text
    assert "export-schema" in text
    assert "neo4j-init" in text
    assert "neo4j-rollback" in text


def test_gateway_help_shows_flags() -> None:
    text = _run_help("gw", "--help")
    assert "--config" in text
    assert "--no-sentinel" in text
    assert "--allow-live" in text


def test_sdk_help_shows_subcommands() -> None:
    text = _run_help("sdk", "--help")
    assert "run" in text
    assert "offline" in text
