"""Top level command line interface for qmtl.

This module exposes a ``main`` function that dispatches the first token as a
subcommand to dedicated modules. Each subcommand implementation lives in
``qmtl.cli.<name>`` (or another module as mapped in ``PRIMARY_DISPATCH``) and
provides ``run(argv)`` which is responsible for its own argument parsing and
execution.

Design note: We avoid ``argparse`` subparsers here so that ``qmtl <cmd> --help``
is forwarded to the actual subcommand parser (e.g., ``qmtl service dagmanager
--help`` prints DAG Manager help, not a placeholder).
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from importlib import import_module
from typing import List


PRIMARY_DISPATCH = {
    "service": "qmtl.cli.service",
    "tools": "qmtl.cli.tools",
    "project": "qmtl.cli.project",
}

LEGACY_ALIASES = {
    "gateway": ("service", ["gateway"]),
    "gw": ("service", ["gateway"]),
    "dagmanager": ("service", ["dagmanager"]),
    "dagmanager-server": ("service", ["dagmanager", "server"]),
    "dagmanager-metrics": ("service", ["dagmanager", "metrics"]),
    "sdk": ("tools", ["sdk"]),
    "taglint": ("tools", ["taglint"]),
    "report": ("tools", ["report"]),
    "init": ("project", ["init"]),
}


def _build_top_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl", add_help=True)
    description = textwrap.dedent(
        """
        Subcommands:
          service   Manage long-running services such as Gateway and DAG Manager.
          tools     Developer tooling including SDK runners and linters.
          project   Project scaffolding and template helpers.

        Legacy aliases (e.g. ``qmtl dagmanager``, ``qmtl gw``, or ``qmtl init``) remain available but emit a
        deprecation warning and forward to the new hierarchy.
        """
    ).strip()
    parser.description = description
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(PRIMARY_DISPATCH.keys()),
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
    if cmd in PRIMARY_DISPATCH:
        module = import_module(PRIMARY_DISPATCH[cmd])
        module.run(rest)
        return

    if cmd in LEGACY_ALIASES:
        target, injected = LEGACY_ALIASES[cmd]
        module = import_module(PRIMARY_DISPATCH[target])
        new_args = injected + rest
        print(
            f"[qmtl] '{cmd}' is deprecated; use 'qmtl {target} {' '.join(injected)}' instead.",
            file=sys.stderr,
        )
        module.run(new_args)
        return

    _build_top_help_parser().print_help()
    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
