"""Validate an existing project structure."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from ..layers import LayerComposer


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``validate`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project validate",
        description="Validate a project created with layered templates",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Project directory to validate (default: current directory)",
    )
    args = parser.parse_args(argv)

    composer = LayerComposer()
    result = composer.validate_project(Path(args.path))

    if result.valid:
        print(f"Project at {args.path} is valid.")
        return

    print(f"Validation failed for project at {args.path}:")
    for error in result.errors:
        print(f"  - {error}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    raise SystemExit(1)
