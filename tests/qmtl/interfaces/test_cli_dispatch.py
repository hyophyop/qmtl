from __future__ import annotations

import pytest

from qmtl.interfaces import cli as top_cli
from tests.qmtl.interfaces._cli_tokens import resolve_cli_tokens


@pytest.mark.parametrize(
    "module_path, expected_phrase",
    [
        ("qmtl.interfaces.cli.project", "Project scaffolding utilities."),
        ("qmtl.interfaces.cli.service", "Manage long-running runtime services."),
        (
            "qmtl.interfaces.cli.tools",
            "Developer tooling for working with strategies and project assets.",
        ),
    ],
)
def test_main_routes_help_to_subcommand(capsys, module_path: str, expected_phrase: str) -> None:
    tokens = resolve_cli_tokens(module_path)

    top_cli.main([*tokens, "--help"])

    output = capsys.readouterr().out
    assert expected_phrase in output


def test_main_reports_unknown_command(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        top_cli.main(["unknown", "--help"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "unknown command" in captured.err
    # Top-level help should still be printed to guide the user
    assert "Subcommands:" in captured.out
