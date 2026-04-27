"""CLI help tests for the v2 command surface."""

from dataclasses import dataclass
from io import StringIO
from contextlib import redirect_stderr, redirect_stdout

from qmtl.interfaces.cli.v2 import main as qmtl_main


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def _run_cli(*args: str) -> CliResult:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            returncode = qmtl_main(list(args))
        except SystemExit as exc:
            returncode = int(exc.code or 0)
    return CliResult(
        returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue()
    )


def _output(result: CliResult) -> str:
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
