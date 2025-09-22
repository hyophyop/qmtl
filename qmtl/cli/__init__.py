"""Top level command line interface for qmtl.

This module exposes a ``main`` function that dispatches the first token as a
subcommand to dedicated modules. Each subcommand implementation lives in
``qmtl.cli.<name>`` (or another module as mapped in ``DISPATCH``) and provides
``run(argv)`` which is responsible for its own argument parsing and execution.

Design note: We avoid ``argparse`` subparsers here so that ``qmtl <cmd> --help``
is forwarded to the actual subcommand parser (e.g., ``qmtl dagmanager --help``
prints DAG Manager help, not a placeholder).
"""

from __future__ import annotations

import argparse
from importlib import import_module
from typing import List
import sys


DISPATCH = {
    "gw": "qmtl.cli.gateway",
    "dagmanager": "qmtl.cli.dagmanager",
    "dagmanager-server": "qmtl.cli.dagmanager_server",
    "dagmanager-metrics": "qmtl.cli.dagmanager_metrics",
    "sdk": "qmtl.cli.sdk",
    "strategies": "qmtl.cli.strategies",
    "doc-sync": "qmtl.cli.doc_sync",
    "check-imports": "qmtl.cli.check_imports",
    "taglint": "qmtl.cli.taglint",
    "report": "qmtl.cli.report",
    "init": "qmtl.cli.init",
}

def _build_top_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl", add_help=True)
    cmds = ", ".join(DISPATCH.keys())
    parser.description = "Subcommands: " + cmds
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(DISPATCH.keys()),
        help="Subcommand to run",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    """Dispatch to subcommand module without consuming its ``--help`` flags."""

    argv = list(argv) if argv is not None else sys.argv[1:]

    # No args or global help → print top-level help
    if not argv or argv[0] in {"-h", "--help"}:
        _build_top_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]
    if cmd not in DISPATCH:
        _build_top_help_parser().print_help()
        raise SystemExit(2)

    module = import_module(DISPATCH[cmd])
    module.run(rest)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
