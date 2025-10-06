"""Seamless stack presets and helpers shipped with the QMTL examples package."""

from importlib import resources as _resources

__all__ = ["get_presets_path", "open_presets"]


def get_presets_path() -> str:
    """Return the filesystem path to the packaged Seamless presets file."""
    return str(_resources.files(__package__).joinpath("presets.yaml"))


def open_presets():
    """Open a text stream for the packaged Seamless presets."""
    return _resources.files(__package__).joinpath("presets.yaml").open("r", encoding="utf-8")
