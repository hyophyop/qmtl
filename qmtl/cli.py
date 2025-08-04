from __future__ import annotations

import argparse
from typing import List


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qmtl")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gw", help="Gateway CLI")
    sub.add_parser("dagm", help="Dag manager admin CLI")
    sub.add_parser("dagmgr-server", help="Run DAG manager servers")
    sub.add_parser("sdk", help="Run strategy via SDK")
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

    args, rest = parser.parse_known_args(argv)

    if args.cmd == "gw":
        from .gateway.cli import main as gw_main
        gw_main(rest)
    elif args.cmd == "dagm":
        from .dagmanager.cli import main as dagm_main
        dagm_main(rest)
    elif args.cmd == "dagmgr-server":
        from .dagmanager.server import main as server_main
        server_main(rest)
    elif args.cmd == "sdk":
        import logging
        from .sdk.cli import main as sdk_main
        logging.basicConfig(level=logging.INFO)
        sdk_main(rest)
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
        )
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
