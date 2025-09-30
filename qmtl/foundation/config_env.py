from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from qmtl.foundation.config import UnifiedConfig

MASK_PLACEHOLDER = "********"
META_KEYS = ("QMTL_CONFIG_SOURCE", "QMTL_CONFIG_EXPORT")

_SECTION_PREFIXES = {
    "gateway": "QMTL__GATEWAY__",
    "dagmanager": "QMTL__DAGMANAGER__",
}

_SECRET_KEYWORDS = ("PASSWORD", "SECRET", "TOKEN", "KEY", "DSN")


@dataclass(frozen=True)
class ConfigEnvVar:
    key: str
    value: str
    secret: bool
    section: str


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        if not value:
            return None
        return ",".join(str(item) for item in value)
    return str(value)


def is_secret_field(name: str) -> bool:
    upper = name.upper()
    return any(token in upper for token in _SECRET_KEYWORDS)


def unified_to_env(unified: UnifiedConfig) -> list[ConfigEnvVar]:
    result: list[ConfigEnvVar] = []
    for section, prefix in _SECTION_PREFIXES.items():
        config_obj = getattr(unified, section)
        data = asdict(config_obj)
        for field, raw_value in sorted(data.items()):
            value = _stringify(raw_value)
            if value is None:
                continue
            secret = is_secret_field(field)
            key = f"{prefix}{field.upper()}"
            result.append(ConfigEnvVar(key=key, value=value, secret=secret, section=section))
    return result


def mask_value(value: str) -> str:
    if not value:
        return value
    return MASK_PLACEHOLDER


def is_managed_key(key: str) -> bool:
    if key in META_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in _SECTION_PREFIXES.values())


def is_secret_key(key: str) -> bool:
    if key in META_KEYS:
        return False
    if "__" not in key:
        return False
    field = key.split("__")[-1]
    return is_secret_field(field)


def collect_managed_keys(
    environ: Mapping[str, str], *, include_missing_meta: bool = False
) -> list[str]:
    keys = {key for key in environ if is_managed_key(key)}
    if include_missing_meta:
        keys.update(META_KEYS)
    else:
        keys.update(key for key in META_KEYS if key in environ)
    return sorted(keys)


__all__ = [
    "ConfigEnvVar",
    "MASK_PLACEHOLDER",
    "META_KEYS",
    "collect_managed_keys",
    "is_managed_key",
    "is_secret_field",
    "is_secret_key",
    "mask_value",
    "unified_to_env",
]
