"""QMTL v2.0 CLI - Simplified command-line interface.

Primary commands:
  submit   Submit a strategy for evaluation and activation
  status   Check status of submitted strategies
  world    World management commands
  init     Initialize a new project

Legacy commands show deprecation messages with migration hints.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, List, cast

from importlib.metadata import PackageNotFoundError, version as pkg_version

from qmtl.utils.i18n import set_language
from qmtl.utils.i18n import _ as _t  # Alias to avoid shadowing in loops

from .http_client import gateway_url
from .status import cmd_status
from .submit import cmd_submit
from .templates import (
    DEFAULT_ENV_EXAMPLE,
    DEFAULT_QMTL_CONFIG,
    DEFAULT_STRATEGY_TEMPLATE,
)
from .world import cmd_world


def cmd_version(argv: List[str]) -> int:
    """Show version information."""
    print(f"QMTL version {_resolve_version()}")
    return 0


def _resolve_version() -> str:
    try:
        return pkg_version("qmtl")
    except PackageNotFoundError:
        return "unknown"


def cmd_init(argv: List[str]) -> int:
    """Initialize a new project."""
    parser = argparse.ArgumentParser(
        prog="qmtl init",
        description=_t("Initialize a new QMTL project"),
    )
    parser.add_argument(
        "path",
        help=_t("Project directory path"),
    )
    parser.add_argument(
        "--preset",
        choices=["minimal", "full"],
        default="minimal",
        help=_t("Project template preset (default: minimal)"),
    )
    
    args = parser.parse_args(argv)
    project_path = Path(args.path)
    if project_path.exists() and any(project_path.iterdir()):
        print(_t("Error: Directory '{}' already exists and is not empty").format(args.path), file=sys.stderr)
        return 1

    project_path.mkdir(parents=True, exist_ok=True)
    strategies_dir = project_path / "strategies"
    strategies_dir.mkdir(parents=True, exist_ok=True)
    (strategies_dir / "__init__.py").write_text("")
    (strategies_dir / "my_strategy.py").write_text(DEFAULT_STRATEGY_TEMPLATE)
    (project_path / "qmtl.yml").write_text(DEFAULT_QMTL_CONFIG)
    (project_path / ".env.example").write_text(DEFAULT_ENV_EXAMPLE)

    print(_t("✅ Project initialized at '{}'").format(args.path))
    print()
    print(_t("Next steps:"))
    print(f"  1. cd {args.path}")
    print("  2. Edit strategies/my_strategy.py with your strategy logic")
    print(
        "  3. qmtl submit strategies.my_strategy:MyStrategy"
        " --world demo_world"
    )
    print("     (project.strategy_root + default_world are tracked in qmtl.yml)")

    return 0


def _build_top_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtl",
        description=_t("QMTL v2.0 Command Line Interface"),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.description = textwrap.dedent(_t("""
        Available commands:
          submit   Submit a strategy for evaluation and activation
          status   Check status of submitted strategies
          world    World management commands
          init     Initialize a new project
    """))
    parser.add_argument("command", nargs="?", help=_t("Command to run"))
    return parser


def _build_admin_help() -> str:
    return textwrap.dedent(_t("""
        Admin/Operator commands:
          gw              Gateway control commands
          gateway         Gateway control commands (alias)
          dagmanager      DAG Manager server controls
          dagmanager-server
                          DAG Manager server controls (alias)
          taglint         Tag validation utility
    """))


CommandHandler = Callable[[List[str]], int]


def _command_tables(admin: bool = False) -> tuple[dict[str, CommandHandler], dict[str, str]]:
    """Return (commands, legacy) tables; admin includes operator commands."""
    commands = {
        "submit": cmd_submit,
        "status": cmd_status,
        "world": cmd_world,
        "init": cmd_init,
        "version": cmd_version,
        "config": lambda argv: int(import_module("qmtl.interfaces.cli.config").run(argv) or 0),
    }
    legacy = {
        "service": "Use 'qmtl submit' for strategy execution, 'qmtl --admin gw' for gateway",
        "tools": "Tools integrated into main commands. Use 'qmtl submit' instead",
        "project": "Use 'qmtl init' for project creation",
        "run": "Use 'qmtl submit' instead",
        "offline": "Use 'qmtl submit' instead",
    }
    if admin:
        commands = {
            **commands,
            "gw": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "gateway": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "dagmanager-server": lambda argv: int(import_module("qmtl.interfaces.cli.dagmanager").run(argv) or 0),
            "taglint": lambda argv: int(import_module("qmtl.interfaces.cli.taglint").run(argv) or 0),
        }
    else:
        commands = {
            **commands,
            "gw": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "gateway": lambda argv: int(import_module("qmtl.interfaces.cli.gateway").run(argv) or 0),
            "dagmanager-server": lambda argv: int(import_module("qmtl.interfaces.cli.dagmanager").run(argv) or 0),
        }
    return cast(tuple[dict[str, CommandHandler], dict[str, str]], (commands, legacy))


# Export command registries for test/inspection without invoking argument parsing
_ALL_COMMANDS, LEGACY_COMMANDS = _command_tables(admin=False)
COMMANDS: dict[str, CommandHandler] = {
    "submit": cmd_submit,
    "status": cmd_status,
    "world": cmd_world,
    "init": cmd_init,
    "version": cmd_version,
}
LEGACY_COMMANDS = {
    **LEGACY_COMMANDS,
    "config": "Use 'qmtl config validate|generate' for configuration utilities",
}
_ADMIN_COMMANDS_FULL, _ = _command_tables(admin=True)
ADMIN_COMMANDS = {
    k: v
    for k, v in _ADMIN_COMMANDS_FULL.items()
    if k not in COMMANDS and k != "config"
}


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
            i += 1
            continue
        rest.append(tok)
        i += 1
    return rest, lang


def main(argv: List[str] | None = None) -> int:
    """Main CLI entry point."""
    argv = list(argv) if argv is not None else sys.argv[1:]
    argv, lang = _extract_lang(argv)
    set_language(lang)

    help_result = _handle_help_requests(argv)
    if help_result is not None:
        return help_result

    admin_mode, cmd, rest = _parse_dispatch_args(argv)
    commands, legacy = _command_tables(admin=admin_mode)

    if cmd in legacy:
        return _print_legacy_warning(cmd, legacy)

    if cmd in commands:
        return _dispatch_command(commands[cmd], rest)

    return _unknown_command(cmd, admin_mode)


def _handle_help_requests(argv: List[str]) -> int | None:
    if not argv or argv[0] in {"-h", "--help"}:
        print("QMTL v2.0 CLI")
        _build_top_help_parser().print_help()
        return 0
    if argv[0] == "--help-admin":
        print(_build_admin_help())
        return 0
    return None


def _parse_dispatch_args(argv: List[str]) -> tuple[bool, str | None, List[str]]:
    admin_mode = False
    if argv and argv[0] == "--admin":
        admin_mode = True
        argv = argv[1:]
    cmd = argv[0] if argv else None
    rest = argv[1:] if len(argv) > 1 else []
    return admin_mode, cmd, rest


def _print_legacy_warning(cmd: str | None, legacy: dict[str, str]) -> int:
    if cmd is None:
        return _unknown_command(cmd, False)
    print(_t("⚠️  Command '{}' has been removed in QMTL v2.0").format(cmd), file=sys.stderr)
    print(_t("   {}").format(legacy[cmd]), file=sys.stderr)
    print(_t("\n   See https://qmtl.readthedocs.io/migrate/v2 for migration guide."), file=sys.stderr)
    return 2


def _dispatch_command(handler: CommandHandler, rest: List[str]) -> int:
    try:
        return handler(rest)
    except KeyboardInterrupt:
        print(_t("\nInterrupted"), file=sys.stderr)
        return 130
    except Exception as e:
        print(_t("Error: {}").format(str(e)), file=sys.stderr)
        return 1


def _unknown_command(cmd: str | None, admin_mode: bool) -> int:
    print(_t("Error: Unknown command '{}'").format(cmd), file=sys.stderr)
    hint = "Run 'qmtl --help' for user commands."
    if not admin_mode:
        hint += " Use 'qmtl --admin --help' for operator commands."
    print(_t(hint), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
