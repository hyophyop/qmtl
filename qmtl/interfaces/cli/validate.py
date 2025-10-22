"""Validate an existing project structure."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List
from qmtl.utils.i18n import _

from ..layers import LayerComposer


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``validate`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project validate",
        description=_("Validate a project created with layered templates"),
    )
    parser.add_argument(
        "--path",
        default=".",
        help=_("Project directory to validate (default: current directory)"),
    )
    args = parser.parse_args(argv)

    composer = LayerComposer()
    result = composer.validate_project(Path(args.path))

    if result.valid:
        print(_("Project at {path} is valid.").format(path=args.path))
        return

    print(_("Validation failed for project at {path}:").format(path=args.path))
    for error in result.errors:
        print(_("  - {error}").format(error=error))
    if result.warnings:
        print(_("Warnings:"))
        for warning in result.warnings:
            print(_("  - {warning}").format(warning=warning))
    raise SystemExit(1)
