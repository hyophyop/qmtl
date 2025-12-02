from __future__ import annotations


def parse_preset_overrides(raw_overrides: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for raw in raw_overrides:
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        try:
            overrides[key] = float(value)
        except Exception:
            continue
    return overrides
