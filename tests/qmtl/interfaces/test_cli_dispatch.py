from __future__ import annotations

import pytest

from qmtl.interfaces import cli as top_cli


@pytest.mark.parametrize(
    "command, expected_phrase",
    [
        ("init", "Initialize a new QMTL project"),
        ("submit", "Submit a strategy"),
        ("status", "Check status"),
    ],
)
def test_main_routes_help_to_subcommand(capsys, command: str, expected_phrase: str) -> None:
    # v2 CLI: flat structure, --help causes SystemExit(0)
    with pytest.raises(SystemExit) as excinfo:
        top_cli.main([command, "--help"])

    assert excinfo.value.code == 0
    output = capsys.readouterr().out
    assert expected_phrase in output


def test_main_reports_unknown_command(capsys) -> None:
    # v2 CLI: unknown commands return 2 (error exit code)
    result = top_cli.main(["unknown", "--help"])
    
    assert result == 2
    captured = capsys.readouterr()
    assert "Unknown command" in captured.err or "unknown command" in captured.err.lower()
