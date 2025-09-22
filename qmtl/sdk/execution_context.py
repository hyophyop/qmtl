from __future__ import annotations

"""Helpers for computing execution context dictionaries.

The Runner previously bundled context normalization, merging, and
resolution logic inside a massive class with substantial state.  This
module extracts the pure functions so they can be imported and tested in
isolation without initializing Runner singletons.
"""

from dataclasses import dataclass
from typing import Mapping, MutableMapping

from qmtl.common.compute_key import DEFAULT_EXECUTION_DOMAIN

_VALID_MODES = {"backtest", "dryrun", "live"}
_CLOCKS = {"virtual", "wall"}


@dataclass(frozen=True)
class ExecutionContextResolution:
    """Result of resolving an execution context."""

    context: dict[str, str]
    force_offline: bool


def normalize_default_context(context: Mapping[str, str] | None) -> dict[str, str] | None:
    """Normalize a default execution context mapping.

    ``Runner.set_default_context`` historically accepted arbitrary
    mapping types and coerced keys/values to strings while skipping
    ``None``.  Moving the logic here keeps the behaviour while enabling
    deterministic tests.
    """

    if context is None:
        return None

    normalized: dict[str, str] = {}
    for key, value in context.items():
        if value is None:
            continue
        normalized[str(key)] = str(value)

    return normalized or None


def _mode_from_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    key = str(domain).strip().lower()
    if key == DEFAULT_EXECUTION_DOMAIN:
        return None
    if key in _VALID_MODES:
        return key
    return None


def _normalize_mode(value: str | None) -> str:
    if value is None:
        raise ValueError("execution_mode must be provided")
    mode = str(value).strip().lower()
    if mode not in _VALID_MODES:
        raise ValueError("execution_mode must be one of 'backtest', 'dryrun', or 'live'")
    return mode


def _validate_clock(value: object, *, expected: str, mode: str | None = None) -> str:
    cval = str(value).strip().lower()
    if cval not in _CLOCKS:
        raise ValueError("clock must be one of 'virtual' or 'wall'")
    if cval != expected:
        if mode:
            raise ValueError(f"{mode} runs require '{expected}' clock but received '{value}'")
        raise ValueError(f"runs require '{expected}' clock but received '{value}'")
    return cval


def merge_context(base: MutableMapping[str, str], source: Mapping[str, str] | None) -> None:
    """Merge ``source`` context values into ``base`` in-place."""

    if not source:
        return
    for key, value in source.items():
        skey = str(key)
        if value is None:
            base.pop(skey, None)
            continue
        base[skey] = str(value)


def resolve_execution_context(
    default_context: Mapping[str, str] | None,
    *,
    context: Mapping[str, str] | None,
    execution_mode: str | None,
    execution_domain: str | None,
    clock: str | None,
    as_of: object | None,
    dataset_fingerprint: str | None,
    offline_requested: bool,
    gateway_url: str | None,
    trade_mode: str,
) -> ExecutionContextResolution:
    """Resolve execution context inputs into a canonical mapping.

    The return value mirrors ``Runner._resolve_context`` prior to
    refactoring while living outside the class for ease of testing.
    """

    merged: dict[str, str] = {}
    if default_context:
        merged.update({str(k): str(v) for k, v in default_context.items()})

    merge_context(merged, context)

    mode: str | None = None
    if execution_mode is not None:
        mode = _normalize_mode(execution_mode)
    else:
        derived = _mode_from_domain(execution_domain)
        if derived is not None:
            mode = derived
    if mode is None:
        domain_hint = merged.get("execution_domain")
        if domain_hint:
            derived = _mode_from_domain(domain_hint)
            if derived is not None:
                mode = derived
    if mode is None:
        existing = merged.get("execution_mode")
        if existing:
            mode = _normalize_mode(existing)
    if mode is None:
        if trade_mode == "live" and not offline_requested:
            mode = "live"
        elif gateway_url and not offline_requested:
            mode = "live"
        else:
            mode = "backtest"

    merged["execution_mode"] = mode
    merged["execution_domain"] = mode

    expected_clock = "wall" if mode == "live" else "virtual"
    if clock is not None:
        merged["clock"] = _validate_clock(clock, expected=expected_clock, mode=mode)
    else:
        existing_clock = merged.get("clock")
        if existing_clock is not None:
            merged["clock"] = _validate_clock(
                existing_clock, expected=expected_clock, mode=mode
            )
        else:
            merged["clock"] = expected_clock

    if as_of is not None:
        text = str(as_of).strip()
        if text:
            merged["as_of"] = text
        else:
            merged.pop("as_of", None)
    elif "as_of" in merged:
        text = str(merged["as_of"]).strip()
        if text:
            merged["as_of"] = text
        else:
            merged.pop("as_of", None)

    if dataset_fingerprint is not None:
        text = str(dataset_fingerprint).strip()
        if text:
            merged["dataset_fingerprint"] = text
        else:
            merged.pop("dataset_fingerprint", None)
    elif "dataset_fingerprint" in merged:
        text = str(merged["dataset_fingerprint"]).strip()
        if text:
            merged["dataset_fingerprint"] = text
        else:
            merged.pop("dataset_fingerprint", None)

    force_offline = False
    if mode != "live":
        has_as_of = bool(merged.get("as_of"))
        has_dataset = bool(merged.get("dataset_fingerprint"))
        if not (has_as_of and has_dataset):
            if gateway_url and not offline_requested:
                force_offline = True
            merged.pop("as_of", None)
            merged.pop("dataset_fingerprint", None)
    else:
        merged.pop("as_of", None)
        merged.pop("dataset_fingerprint", None)

    return ExecutionContextResolution(context=merged, force_offline=force_offline)


__all__ = [
    "ExecutionContextResolution",
    "merge_context",
    "normalize_default_context",
    "resolve_execution_context",
]
