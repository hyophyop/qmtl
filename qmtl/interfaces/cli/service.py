from __future__ import annotations

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
            Manage long-running runtime services.

            Available services:
              gateway     Run the Gateway HTTP API.
              dagmanager  Operate DAG Manager utilities and daemons.
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
