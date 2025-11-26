from __future__ import annotations

"""Service management CLI module.

This module provides access to QMTL services:
- gateway: HTTP API server
- dagmanager: DAG orchestration server

Note: In QMTL v2.0, services are auto-discovered via environment variables.
You can still use this module to manually start services for development.
"""

import argparse
import textwrap
from importlib import import_module
from typing import List
from qmtl.utils.i18n import _


SERVICE_DISPATCH = {
    "gateway": "qmtl.interfaces.cli.gateway",
    "dagmanager": "qmtl.interfaces.cli.dagmanager",
}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl service", add_help=True)
    parser.description = textwrap.dedent(
        _(
            """
            Manage QMTL runtime services.

            Available services:
              gateway     Run the Gateway HTTP API.
              dagmanager  Operate DAG Manager utilities and daemons.
              
            Note: In v2.0, services are auto-discovered. Use QMTL_GATEWAY_URL
            environment variable to configure the gateway URL.
            """
        )
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(SERVICE_DISPATCH.keys()),
        help=_("Service to manage"),
    )
    return parser


def run(argv: List[str] | None = None) -> None:
    """Run service command."""
    argv = list(argv) if argv is not None else []

    if not argv or argv[0] in {"-h", "--help"}:
        _build_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]
    if cmd not in SERVICE_DISPATCH:
        _build_help_parser().print_help()
        raise SystemExit(2)

    module = import_module(SERVICE_DISPATCH[cmd])
    module.run(rest)


if __name__ == "__main__":  # pragma: no cover
    run()
