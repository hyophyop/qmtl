from __future__ import annotations

import argparse
import textwrap
from importlib import import_module
from typing import List
from qmtl.utils.i18n import _


PROJECT_DISPATCH = {
    "init": "qmtl.interfaces.cli.init",
    "layer": "qmtl.interfaces.cli.layer",
    "list-presets": "qmtl.interfaces.cli.presets",
}

LEGACY_LAYER_ALIASES = {
    "add-layer": "add",
    "list-layers": "list",
    "validate": "validate",
}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl project", add_help=True)
    parser.description = textwrap.dedent(
        _(
            """
            Project scaffolding utilities.

            Available commands:
              init          Create a new strategy project from templates or presets.
              layer         Manage project layers (add, list, validate).
              list-presets  List available presets (and optional legacy templates).

            Legacy aliases:
              add-layer     → layer add
              list-layers   → layer list
              validate      → layer validate
            """
        )
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(PROJECT_DISPATCH.keys()),
        help=_("Project command to run"),
    )
    return parser


def run(argv: List[str] | None = None) -> None:
    argv = list(argv) if argv is not None else []

    if not argv or argv[0] in {"-h", "--help"}:
        _build_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]
    if cmd in LEGACY_LAYER_ALIASES:
        from . import layer as layer_module

        layer_module.run([LEGACY_LAYER_ALIASES[cmd], *rest])
        return

    if cmd not in PROJECT_DISPATCH:
        _build_help_parser().print_help()
        raise SystemExit(2)

    module = import_module(PROJECT_DISPATCH[cmd])
    module.run(rest)


if __name__ == "__main__":  # pragma: no cover
    run()
