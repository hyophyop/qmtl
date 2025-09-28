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

    if "preset" in config:
        name = config["preset"]
        if not isinstance(name, str):
            raise TypeError("'preset' must be a string")
        options = _as_mapping(config.get("options"), "options")
        entries.append((name, options))

    if "presets" in config:
        raw_presets = config["presets"]
        if isinstance(raw_presets, str):
            entries.append((raw_presets, {}))
        elif isinstance(raw_presets, Mapping):
            # single mapping entry
            preset_name = raw_presets.get("name") or raw_presets.get("preset")
            if not isinstance(preset_name, str):
                raise KeyError("preset mapping requires 'name' or 'preset'")
            options = _as_mapping(
                raw_presets.get("config") or raw_presets.get("options"),
                "presets.options",
            )
            entries.append((preset_name, options))
        elif isinstance(raw_presets, Sequence):
            for idx, entry in enumerate(raw_presets):
                if isinstance(entry, str):
                    entries.append((entry, {}))
                    continue
                if isinstance(entry, Mapping):
                    preset_name = entry.get("name") or entry.get("preset")
                    if not isinstance(preset_name, str):
                        raise KeyError(
                            f"presets[{idx}] mapping requires 'name' or 'preset'"
                        )
                    options = _as_mapping(
                        entry.get("config") or entry.get("options"),
                        f"presets[{idx}].options",
                    )
                    entries.append((preset_name, options))
                    continue
                raise TypeError(
                    f"unsupported presets[{idx}] entry type: {type(entry)!r}"
                )
        elif raw_presets is not None:
            raise TypeError("'presets' must be string, mapping, or sequence")

    for name, options in entries:
        result = SeamlessPresetRegistry.apply(name, builder=result, config=options)

    return result


def build_assembly(
    config: Mapping[str, Any],
    *,
    builder: Optional[SeamlessBuilder] = None,
):
    """Hydrate a builder using ``config`` and return the resulting assembly."""

    updated = hydrate_builder(config, builder=builder)
    return updated.build()


__all__ = ["hydrate_builder", "build_assembly"]
