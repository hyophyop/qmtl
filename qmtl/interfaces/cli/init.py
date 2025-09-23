from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from ..scaffold import TEMPLATES, create_project


def run(argv: List[str] | None = None) -> None:
    """Entry point for the ``init`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project init",
        description="Initialize new project (see docs/guides/strategy_workflow.md)",
    )
    parser.add_argument("--path", required=True, help="Project directory to create scaffolding")
    parser.add_argument(
        "--strategy",
        default="general",
        help="Strategy template to use (see docs/reference/templates.md)",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available templates and exit (see docs/reference/templates.md)",
    )
    parser.add_argument(
        "--with-sample-data",
        action="store_true",
        help="Include sample OHLCV CSV and notebook (see docs/guides/strategy_workflow.md)",
    )
    parser.add_argument("--with-docs", action="store_true", help="Include docs/ directory template")
    parser.add_argument("--with-scripts", action="store_true", help="Include scripts/ directory template")
    parser.add_argument("--with-pyproject", action="store_true", help="Include pyproject.toml template")

    args = parser.parse_args(argv)

    if args.list_templates:
        for name in TEMPLATES:
            print(name)
        return

    create_project(
        Path(args.path),
        template=args.strategy,
        with_sample_data=args.with_sample_data,
        with_docs=args.with_docs,
        with_scripts=args.with_scripts,
        with_pyproject=args.with_pyproject,
    )

