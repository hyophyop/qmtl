"""Layer-oriented project helpers dispatched under ``qmtl project layer``."""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Callable, Dict, Iterable, List

from qmtl.utils.i18n import _

from ..layers import Layer, LayerComposer, load_layer_metadata


Handler = Callable[[List[str] | None], None]


def _parse_layer_token(raw: str) -> Layer:
    """Parse a layer token and emit a helpful error message on failure."""

    try:
        return Layer(raw)
    except ValueError:
        print(_("Error: Invalid layer '{layer}'").format(layer=raw), file=sys.stderr)
        print(_("\nAvailable layers:"), file=sys.stderr)
        for option in Layer:
            print(_("  {value}").format(value=option.value), file=sys.stderr)
        raise SystemExit(1)


def _emit_validation_failure(
    heading: str,
    *,
    errors: Iterable[str],
    warnings: Iterable[str] | None,
    stream,
) -> None:
    """Print validation errors/warnings and exit."""

    print(heading, file=stream)
    for error in errors:
        print(_("  - {error}").format(error=error), file=stream)
    warning_list = list(warnings or [])
    if warning_list:
        print(_("Warnings:"), file=stream)
        for warning in warning_list:
            print(_("  - {warning}").format(warning=warning), file=stream)
    raise SystemExit(1)


def _build_add_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtl project layer add",
        description=_("Add a layer to an existing project"),
    )
    parser.add_argument(
        "--path",
        default=".",
        help=_("Project directory (default: current directory)"),
    )
    parser.add_argument(
        "layer",
        help=_("Layer to add (data, signal, execution, brokerage, monitoring)"),
    )
    parser.add_argument(
        "--template",
        help=_("Specific template to use for this layer"),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=_("Force overwrite if layer already exists"),
    )
    return parser


def _build_list_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtl project layer list",
        description=_("List available layers and their metadata"),
    )
    parser.add_argument(
        "--show-templates",
        action="store_true",
        help=_("Include template names for each layer"),
    )
    parser.add_argument(
        "--show-requires",
        action="store_true",
        help=_("Include dependency information for templates"),
    )
    return parser


def _build_validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmtl project layer validate",
        description=_("Validate a project created with layered templates"),
    )
    parser.add_argument(
        "--path",
        default=".",
        help=_("Project directory to validate (default: current directory)"),
    )
    return parser


def _handle_add(argv: List[str] | None = None) -> None:
    parser = _build_add_parser()
    args = parser.parse_args(argv)

    layer = _parse_layer_token(args.layer)

    composer = LayerComposer()
    result = composer.add_layer(
        dest=Path(args.path),
        layer=layer,
        template_name=args.template,
        force=args.force,
    )

    if not result.valid:
        _emit_validation_failure(
            heading=_("Error adding layer:"),
            errors=result.errors,
            warnings=result.warnings,
            stream=sys.stderr,
        )

    print(_("Layer '{name}' added to project at {path}").format(name=layer.value, path=args.path))
    if args.template:
        print(_("Using template: {template}").format(template=args.template))


def _handle_list(argv: List[str] | None = None) -> None:
    parser = _build_list_parser()
    args = parser.parse_args(argv)

    print(_("Available layers:"))
    for layer in Layer:
        metadata = load_layer_metadata(layer)
        print(_("  {value:12} - {desc}").format(value=layer.value, desc=metadata.description))
        if args.show_templates and metadata.templates:
            for template in metadata.templates:
                requires = ""
                if args.show_requires and template.requires:
                    requires = _(" (requires: {req})").format(req=", ".join(template.requires))
                print(
                    _("    • {name}{req} - {desc}").format(
                        name=template.name,
                        req=requires,
                        desc=template.description,
                    )
                )


def _handle_validate(argv: List[str] | None = None) -> None:
    parser = _build_validate_parser()
    args = parser.parse_args(argv)

    composer = LayerComposer()
    result = composer.validate_project(Path(args.path))

    if result.valid:
        print(_("Project at {path} is valid.").format(path=args.path))
        return

    _emit_validation_failure(
        heading=_("Validation failed for project at {path}:").format(path=args.path),
        errors=result.errors,
        warnings=result.warnings,
        stream=sys.stdout,
    )


LAYER_HANDLERS: Dict[str, Handler] = {
    "add": _handle_add,
    "list": _handle_list,
    "validate": _handle_validate,
}


LAYER_DISPATCH: Dict[str, str] = {}


def _build_help_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qmtl project layer", add_help=True)
    parser.description = textwrap.dedent(
        _(
            """
            Manage project layers.

            Available commands:
              add       Add a layer to an existing project.
              list      List available layers and metadata.
              validate  Validate an existing layered project.
            """
        )
    ).strip()
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=sorted(LAYER_HANDLERS.keys()),
        help=_("Layer command to run"),
    )
    return parser


def run(argv: List[str] | None = None) -> None:
    argv = list(argv) if argv is not None else []

    if not argv or argv[0] in {"-h", "--help"}:
        _build_help_parser().print_help()
        return

    cmd = argv[0]
    rest = argv[1:]

    handler = LAYER_HANDLERS.get(cmd)
    if handler is None:
        _build_help_parser().print_help()
        raise SystemExit(2)

    handler(rest)


def run_add(argv: List[str] | None = None) -> None:
    """Compatibility wrapper for legacy ``add-layer`` entry point."""

    _handle_add(argv)


def run_list(argv: List[str] | None = None) -> None:
    """Compatibility wrapper for legacy ``list-layers`` entry point."""

    _handle_list(argv)


def run_validate(argv: List[str] | None = None) -> None:
    """Compatibility wrapper for legacy ``validate`` entry point."""

    _handle_validate(argv)


if __name__ == "__main__":  # pragma: no cover
    run()
