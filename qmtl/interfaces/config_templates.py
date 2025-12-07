"""Helpers for accessing packaged configuration templates."""

from __future__ import annotations

import importlib.resources as resources
from pathlib import Path
from typing import Iterable

__all__ = [
    "CONFIG_TEMPLATE_FILES",
    "available_profiles",
    "resolve_template",
    "write_template",
]

CONFIG_TEMPLATE_FILES = {
    # Preferred names aligned with deployment profiles
    "dev": "qmtl.minimal.yml",
    "prod": "qmtl.maximal.yml",
    # Backward-compatible aliases
    "minimal": "qmtl.minimal.yml",
    "maximal": "qmtl.maximal.yml",
}


def available_profiles() -> Iterable[str]:
    """Return the supported configuration template profiles."""

    return CONFIG_TEMPLATE_FILES.keys()


def resolve_template(profile: str):
    """Return a package resource handle for the requested profile."""

    try:
        filename = CONFIG_TEMPLATE_FILES[profile]
    except KeyError as exc:  # pragma: no cover - argparse prevents invalid choices
        raise ValueError(f"Unknown configuration profile: {profile}") from exc

    base = resources.files("qmtl.examples").joinpath("templates", "config")
    template = base.joinpath(filename)
    if not template.is_file():  # pragma: no cover - defensive guard
        raise FileNotFoundError(f"Template for profile '{profile}' not found")
    return template


def write_template(profile: str, output: Path, *, force: bool = False) -> Path:
    """Write the requested configuration template to *output*.

    Args:
        profile: Template profile name to write.
        output: Destination path for the rendered template.
        force: Allow overwriting an existing file when ``True``.

    Returns:
        The path that was written.
    """

    output = Path(output)
    if output.exists() and not force:
        raise FileExistsError(f"{output} already exists")

    template = resolve_template(profile)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(template.read_bytes())
    return output
