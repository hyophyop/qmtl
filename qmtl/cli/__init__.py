"""Top level command line interface for qmtl.

This module exposes a ``main`` function that parses the first level of
subcommands and dispatches remaining arguments to dedicated modules.  Each
subcommand implementation lives in ``qmtl.cli.<name>`` and provides a
``run(argv)`` entry point which is responsible for its own argument parsing
and execution.
"""

from __future__ import annotations

import argparse
from importlib import import_module
from typing import List


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
    "init": "qmtl.cli.init",
}


def main(argv: List[str] | None = None) -> None:
    """Parse the top-level CLI and forward to a subcommand module."""

    parser = argparse.ArgumentParser(prog="qmtl")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("gw", help="Gateway CLI")
    sub.add_parser("dagmanager", help="DAG Manager admin CLI")
    sub.add_parser("dagmanager-server", help="Run DAG Manager servers")
    sub.add_parser("dagmanager-metrics", help="Expose DAG Manager metrics")
    sub.add_parser("sdk", help="Run strategy via SDK")
    sub.add_parser("strategies", help="Run local strategies")
    sub.add_parser(
        "doc-sync",
        help="Verify alignment between docs, registry, and module annotations",
    )
    sub.add_parser(
        "check-imports", help="Fail if qmtl imports local strategies package"
    )
    sub.add_parser("taglint", help="Lint TAGS dictionaries")
    sub.add_parser(
        "init",
        help="Initialize new project (see docs/guides/strategy_workflow.md)",
    )

    args, rest = parser.parse_known_args(argv)

    module = import_module(DISPATCH[args.cmd])
    module.run(rest)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

