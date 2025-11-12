"""List available project presets."""

from __future__ import annotations

import argparse

from qmtl.utils.i18n import _

from ..layers import PresetLoader
from ..scaffold import TEMPLATES


def run(argv: list[str] | None = None) -> None:
    """Entry point for the ``list-presets`` subcommand."""

    parser = argparse.ArgumentParser(
        prog="qmtl project list-presets",
        description=_("List available presets for layered project scaffolds"),
    )
    parser.add_argument(
        "--show-legacy-templates",
        action="store_true",
        help=_("Include deprecated template names (from qmtl.interfaces.scaffold.TEMPLATES)"),
    )
    args = parser.parse_args(argv)

    loader = PresetLoader()
    print(_("Available presets:"))
    for preset_name in loader.list_presets():
        preset = loader.get_preset(preset_name)
        if not preset:
            continue
        print(
            _("  {name:15} - {desc}").format(
                name=preset_name,
                desc=preset.description,
            )
        )

    if args.show_legacy_templates:
        print(_("\nAvailable legacy templates:"))
        for template_name in sorted(TEMPLATES):
            print(template_name)


if __name__ == "__main__":  # pragma: no cover
    run()
