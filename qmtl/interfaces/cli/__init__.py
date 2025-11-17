"""Top level command line interface for qmtl.

This module exposes a ``main`` function that dispatches the first token as a
subcommand to dedicated modules. Each subcommand implementation lives in
``qmtl.interfaces.cli.<name>`` (or another module as mapped in ``PRIMARY_DISPATCH``) and
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
from qmtl.utils.i18n import _, set_language


PRIMARY_DISPATCH = {
    "config": "qmtl.interfaces.cli.config",
    "service": "qmtl.interfaces.cli.service",
    "tools": "qmtl.interfaces.cli.tools",
    "project": "qmtl.interfaces.cli.project",
}


def _build_top_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl", add_help=True)
    description = textwrap.dedent(
        _(
            """
            Subcommands:
              config    Validate gateway and DAG Manager configuration files.
              service   Manage long-running services such as Gateway and DAG Manager.
              tools     Developer tooling including SDK runners and linters.
              project   Project scaffolding and template helpers.

            Global options:
              --lang {en,ko}  Override CLI language (default: auto)
            """
        )
    ).strip()
    parser.description = description
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(PRIMARY_DISPATCH.keys()),
        help=_("Subcommand to run"),
    )
    return parser


def _extract_lang(argv: List[str]) -> tuple[List[str], str | None]:
    """Extract --lang/-L from argv; return (rest, lang)."""
    rest: List[str] = []
    lang: str | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--lang="):
            lang = tok.split("=", 1)[1]
            i += 1
            continue
        if tok == "--lang" or tok == "-L":
            if i + 1 < len(argv):
                lang = argv[i + 1]
                i += 2
                continue
            # dangling --lang -> ignore
            i += 1
            continue
        rest.append(tok)
        i += 1
    return rest, lang


def main(argv: List[str] | None = None) -> int:
    """Dispatch to subcommand module without consuming its ``--help`` flags.

    Returns an exit status suitable for ``sys.exit``.
    """

    argv = list(argv) if argv is not None else sys.argv[1:]

    # Global language override (does not consume subcommand options)
    argv, lang = _extract_lang(argv)
    set_language(lang)

    # No args or global help → print top-level help
    if not argv or argv[0] in {"-h", "--help"}:
        _build_top_help_parser().print_help()
        return 0

    cmd = argv[0]
    rest = argv[1:]
    if cmd in PRIMARY_DISPATCH:
        module = import_module(PRIMARY_DISPATCH[cmd])
        result = module.run(rest)
        if isinstance(result, int):
            return result
        return 0

    parser = _build_top_help_parser()
    parser.print_help()
    print(_("\nerror: unknown command '{cmd}'").format(cmd=cmd), file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
