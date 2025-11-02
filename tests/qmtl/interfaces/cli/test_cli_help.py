import subprocess
import sys

from tests.qmtl.interfaces._cli_tokens import resolve_cli_tokens


def _run_help(*args: str) -> str:
    cmd = [sys.executable, "-m", "qmtl", *args]
    out = subprocess.run(cmd, capture_output=True, text=True)
    # argparse writes help to stdout by default; fallback to stderr if empty
    return out.stdout or out.stderr


def test_dagmanager_help_shows_subcommands() -> None:
    tokens = resolve_cli_tokens("qmtl.interfaces.cli.service", "qmtl.interfaces.cli.dagmanager")
    text = _run_help(*tokens, "--help")
    assert "diff" in text
    assert "export-schema" in text
    assert "neo4j-init" in text
    assert "neo4j-rollback" in text


def test_gateway_help_shows_flags() -> None:
    tokens = resolve_cli_tokens("qmtl.interfaces.cli.service", "qmtl.interfaces.cli.gateway")
    text = _run_help(*tokens, "--help")
    assert "--config" in text
    assert "--no-sentinel" in text
    assert "--allow-live" in text


def test_sdk_help_shows_subcommands() -> None:
    tokens = resolve_cli_tokens("qmtl.interfaces.cli.tools", "qmtl.interfaces.cli.sdk")
    text = _run_help(*tokens, "--help")
    assert "run" in text
    assert "offline" in text
