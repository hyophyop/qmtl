from __future__ import annotations

import argparse
import textwrap
from importlib import import_module
from typing import List
from qmtl.utils.i18n import _


TOOLS_DISPATCH = {
    "sdk": "qmtl.interfaces.cli.sdk",
    "taglint": "qmtl.interfaces.cli.taglint",
    "report": "qmtl.interfaces.cli.report",
}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl tools", add_help=True)
    parser.description = textwrap.dedent(
        _(
            """
            Developer tooling for working with strategies and project assets.

            Available tools:
              sdk      Execute strategies in run/offline modes.
              taglint  Validate TAGS dictionaries in project code.
              report   Generate performance reports from JSON returns.
            """
        )
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(TOOLS_DISPATCH.keys()),
        help=_("Tool to invoke"),
    )
    return parser


def run(argv: List[str] | None = None) -> None:
    argv = list(argv) if argv is not None else []

    if not argv or argv[0] in {"-h", "--help"}:
        _build_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]
    if cmd not in TOOLS_DISPATCH:
        _build_help_parser().print_help()
        raise SystemExit(2)

    module = import_module(TOOLS_DISPATCH[cmd])
    module.run(rest)


if __name__ == "__main__":  # pragma: no cover
    run()
