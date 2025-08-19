from __future__ import annotations

import argparse
from typing import List


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qmtl")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gw", help="Gateway CLI")
    sub.add_parser("dagmanager", help="DAG Manager admin CLI")
    sub.add_parser("dagmanager-server", help="Run DAG Manager servers")
    sub.add_parser("dagmanager-metrics", help="Expose DAG Manager metrics")
    sub.add_parser("sdk", help="Run strategy via SDK")
    sub.add_parser("taglint", help="Validate TAGS metadata")
    p_init = sub.add_parser(
        "init",
        help="Initialize new project (see docs/strategy_workflow.md)",
    )
    p_init.add_argument(
        "--path", required=True, help="Project directory to create scaffolding"
    )
    p_init.add_argument(
        "--strategy",
        default="general",
        help="Strategy template to use (see docs/templates.md)",
    )
    p_init.add_argument(
        "--list-templates",
        action="store_true",
        help="List available templates and exit (see docs/templates.md)",
    )
    p_init.add_argument(
        "--with-sample-data",
        action="store_true",
        help="Include sample OHLCV CSV and notebook (see docs/strategy_workflow.md)",
    )
    p_init.add_argument(
        "--with-docs",
        action="store_true",
        help="Include docs/ directory template",
    )
    p_init.add_argument(
        "--with-scripts",
        action="store_true",
        help="Include scripts/ directory template",
    )
    p_init.add_argument(
        "--with-pyproject",
        action="store_true",
        help="Include pyproject.toml template",
    )

    args, rest = parser.parse_known_args(argv)

    if args.cmd == "gw":
        from .gateway.cli import main as gw_main
        gw_main(rest)
    elif args.cmd == "dagmanager":
        from .dagmanager.cli import main as dagm_main
        dagm_main(rest)
    elif args.cmd == "dagmanager-server":
        from .dagmanager.server import main as server_main
        server_main(rest)
    elif args.cmd == "dagmanager-metrics":
        from .dagmanager.metrics import main as metrics_main
        metrics_main(rest)
    elif args.cmd == "sdk":
        import logging
        from .sdk.cli import main as sdk_main
        logging.basicConfig(level=logging.INFO)
        sdk_main(rest)
    elif args.cmd == "taglint":
        from qmtl.tools.taglint import main as taglint_main
        taglint_main(rest)
    elif args.cmd == "init":
        from pathlib import Path
        from .scaffold import create_project, TEMPLATES

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
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
