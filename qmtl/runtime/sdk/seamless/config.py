from __future__ import annotations

"""Helpers to hydrate Seamless builders from configuration mappings."""

from typing import Any, Mapping, Optional, Sequence

from .builder import SeamlessBuilder, SeamlessPresetRegistry


def _as_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"expected mapping for '{field}', got {type(value)!r}")


def hydrate_builder(
    config: Mapping[str, Any],
    *,
    builder: Optional[SeamlessBuilder] = None,
) -> SeamlessBuilder:
    """Apply presets described by ``config`` to a :class:`SeamlessBuilder`.

    Supported keys (all optional):
        ``preset``: single preset name (string).
        ``options``: mapping of options for the single preset.
        ``presets``: sequence of preset entries. Each entry may be a string name or a
            mapping with ``name``/``preset`` and optional ``config``/``options``.

    Returns the updated builder (creating a new one when not provided).
    """

    if not isinstance(config, Mapping):
        raise TypeError("config must be a mapping")

    result = builder or SeamlessBuilder()
    entries: list[tuple[str, Mapping[str, Any]]] = []

    single = _extract_single_preset(config)
    if single:
        entries.append(single)

    entries.extend(_extract_presets(config.get("presets")))

    for name, options in entries:
        result = SeamlessPresetRegistry.apply(name, builder=result, config=options)

    return result


def _extract_single_preset(config: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    if "preset" not in config:
        return None
    name = config["preset"]
    if not isinstance(name, str):
        raise TypeError("'preset' must be a string")
    options = _as_mapping(config.get("options"), "options")
    return name, options


def _extract_presets(raw_presets: Any) -> list[tuple[str, Mapping[str, Any]]]:
    if raw_presets is None:
        return []
    if isinstance(raw_presets, str):
        return [(raw_presets, {})]
    if isinstance(raw_presets, Mapping):
        return [_parse_preset_mapping(raw_presets, "presets")]
    if isinstance(raw_presets, Sequence):
        return [_parse_sequence_entry(entry, idx) for idx, entry in enumerate(raw_presets)]
    raise TypeError("'presets' must be string, mapping, or sequence")


def _parse_sequence_entry(entry: Any, idx: int) -> tuple[str, Mapping[str, Any]]:
    if isinstance(entry, str):
        return entry, {}
    if isinstance(entry, Mapping):
        return _parse_preset_mapping(entry, f"presets[{idx}]")
    raise TypeError(f"unsupported presets[{idx}] entry type: {type(entry)!r}")


def _parse_preset_mapping(entry: Mapping[str, Any], path: str) -> tuple[str, Mapping[str, Any]]:
    preset_name = entry.get("name") or entry.get("preset")
    if not isinstance(preset_name, str):
        raise KeyError(f"{path} mapping requires 'name' or 'preset'")
    options = _as_mapping(entry.get("config") or entry.get("options"), f"{path}.options")
    return preset_name, options


def build_assembly(
    config: Mapping[str, Any],
    *,
    builder: Optional[SeamlessBuilder] = None,
):
    """Hydrate a builder using ``config`` and return the resulting assembly."""

    updated = hydrate_builder(config, builder=builder)
    return updated.build()


__all__ = ["hydrate_builder", "build_assembly"]
