from __future__ import annotations

from unittest import mock

from qmtl.interfaces import cli as top_cli


def test_dispatch_init():
    with mock.patch("qmtl.interfaces.cli.init.run") as run:
        top_cli.main(["init", "--path", "p"])
        run.assert_called_once_with(["--path", "p"])


def test_dispatch_gateway():
    with mock.patch("qmtl.interfaces.cli.gateway.run") as run:
        top_cli.main(["gw", "arg1"])
        run.assert_called_once_with(["arg1"])

