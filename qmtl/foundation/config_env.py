from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Set

from qmtl.foundation.config import (
    CONFIG_SECTION_NAMES,
    ENV_EXPORT_IGNORED_FIELDS,
    ENV_EXPORT_OVERRIDES,
    ENV_EXPORT_PREFIXES,
    UnifiedConfig,
)

MASK_PLACEHOLDER = "********"
META_KEYS = ("QMTL_CONFIG_SOURCE", "QMTL_CONFIG_EXPORT")

_MANAGED_PREFIXES: tuple[str, ...] = tuple(sorted(set(ENV_EXPORT_PREFIXES.values())))
_OVERRIDE_KEYS: Set[str] = {
    env
    for overrides in ENV_EXPORT_OVERRIDES.values()
    for env in overrides.values()
    if env
}
_ENV_TO_FIELD: Dict[str, str] = {
    env: field
    for section_overrides in ENV_EXPORT_OVERRIDES.values()
    for field, env in section_overrides.items()
    if env
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
    seen: Set[str] = set()
    for section in CONFIG_SECTION_NAMES:
        config_obj = getattr(unified, section, None)
        if config_obj is None:
            continue
        data = asdict(config_obj)
        prefix = ENV_EXPORT_PREFIXES.get(section)
        overrides = ENV_EXPORT_OVERRIDES.get(section, {})
        ignored = ENV_EXPORT_IGNORED_FIELDS.get(section, set())
        for field, raw_value in sorted(data.items()):
            if field in ignored:
                continue
            key = overrides.get(field)
            if key is None and prefix:
                key = f"{prefix}{field.upper()}"
            if not key or key in seen:
                continue
            value = _stringify(raw_value)
            if value is None:
                continue
            secret = is_secret_field(field)
            result.append(ConfigEnvVar(key=key, value=value, secret=secret, section=section))
            seen.add(key)
    return result


def mask_value(value: str) -> str:
    if not value:
        return value
    return MASK_PLACEHOLDER


def is_managed_key(key: str) -> bool:
    if key in META_KEYS:
        return True
    if any(prefix and key.startswith(prefix) for prefix in _MANAGED_PREFIXES):
        return True
    return key in _OVERRIDE_KEYS


def is_secret_key(key: str) -> bool:
    if key in META_KEYS:
        return False
    field = None
    if key in _ENV_TO_FIELD:
        field = _ENV_TO_FIELD[key]
    elif "__" in key:
        field = key.split("__")[-1]
    if field is None:
        return False
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
