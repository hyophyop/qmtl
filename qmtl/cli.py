from __future__ import annotations

import argparse
from typing import List


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="qmtl")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gw", help="Gateway CLI", add_help=False)
    sub.add_parser("dagm", help="Dag manager admin CLI", add_help=False)
    sub.add_parser("dagmgr-server", help="Run DAG manager servers", add_help=False)
    sub.add_parser("sdk", help="Run strategy via SDK", add_help=False)

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
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
