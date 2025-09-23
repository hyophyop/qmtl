from __future__ import annotations

import argparse
import textwrap
from importlib import import_module
from typing import List


PROJECT_DISPATCH = {
    "init": "qmtl.cli.init",
}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl project", add_help=True)
    parser.description = textwrap.dedent(
        """
        Project scaffolding utilities.

        Available commands:
          init  Create a new strategy project from templates.
        """
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(PROJECT_DISPATCH.keys()),
        help="Project command to run",
    )
    return parser


def run(argv: List[str] | None = None) -> None:
    argv = list(argv) if argv is not None else []

    if not argv or argv[0] in {"-h", "--help"}:
        _build_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]
    if cmd not in PROJECT_DISPATCH:
        _build_help_parser().print_help()
        raise SystemExit(2)

    module = import_module(PROJECT_DISPATCH[cmd])
    module.run(rest)


if __name__ == "__main__":  # pragma: no cover
    run()
