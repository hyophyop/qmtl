from __future__ import annotations

from unittest import mock

from qmtl.interfaces import cli as top_cli
from tests.qmtl.interfaces._cli_tokens import resolve_cli_tokens


def test_dispatch_init():
    with mock.patch("qmtl.interfaces.cli.init.run") as run:
        tokens = resolve_cli_tokens("qmtl.interfaces.cli.project", "qmtl.interfaces.cli.init")
        top_cli.main([*tokens, "--path", "p"])
        run.assert_called_once_with(["--path", "p"])


def test_dispatch_gateway():
    with mock.patch("qmtl.interfaces.cli.gateway.run") as run:
        tokens = resolve_cli_tokens("qmtl.interfaces.cli.service", "qmtl.interfaces.cli.gateway")
        top_cli.main([*tokens, "arg1"])
        run.assert_called_once_with(["arg1"])
