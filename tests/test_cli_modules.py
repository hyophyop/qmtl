from __future__ import annotations

from unittest import mock


def test_gateway_run_invokes_gateway_main():
    with mock.patch("qmtl.gateway.cli.main") as gw_main:
        from qmtl.cli import gateway

        gateway.run(["--foo"])
        gw_main.assert_called_once_with(["--foo"])


def test_dagmanager_run_invokes_dagmanager_main():
    with mock.patch("qmtl.dagmanager.cli.main") as dag_main:
        from qmtl.cli import dagmanager

        dagmanager.run(["--bar"])
        dag_main.assert_called_once_with(["--bar"])

