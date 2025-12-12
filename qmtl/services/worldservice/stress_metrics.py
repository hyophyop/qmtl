"""Helper utilities to normalize stress scenario metrics."""

from __future__ import annotations

from typing import Any, Dict, Mapping


def normalize_stress_metrics(
    metrics: Mapping[str, Any],
    *,
    scenarios: Mapping[str, Mapping[str, float]] | None = None,
) -> Dict[str, float]:
    """Flatten stress scenario metrics to dot-path keys.

    Input examples:
        {"stress": {"crash": {"max_drawdown": 0.3, "es_99": 0.2}}}
        {"stress.crash.max_drawdown": 0.3}
    Output:
        {"stress.crash.max_drawdown": 0.3, "stress.crash.es_99": 0.2}
    """
    flat: Dict[str, float] = {}
    for key, value in metrics.items():
        if key == "stress" and isinstance(value, Mapping):
            for name, vals in value.items():
                if not isinstance(vals, Mapping):
                    continue
                for sub, v in vals.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        flat[f"stress.{name}.{sub}"] = float(v)
        elif key.startswith("stress.") and isinstance(value, (int, float)) and not isinstance(value, bool):
            flat[key] = float(value)
    # Ensure scenario keys exist even if missing
    if scenarios:
        for name, fields in scenarios.items():
            for field in fields.keys():
                flat.setdefault(f"stress.{name}.{field}", flat.get(f"stress.{name}.{field}"))
    return flat


__all__ = ["normalize_stress_metrics"]
