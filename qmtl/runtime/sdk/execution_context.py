from __future__ import annotations

"""Helpers for computing execution context dictionaries.

The Runner previously bundled context normalization, merging, and
resolution logic inside a massive class with substantial state.  This
module extracts the pure functions so they can be imported and tested in
isolation without initializing Runner singletons.
"""

from typing import Mapping, MutableMapping

from qmtl.runtime.helpers import (
    ExecutionContextResolution,
    apply_temporal_requirements,
    determine_execution_mode,
    normalize_clock_value,
)


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

    mode = determine_execution_mode(
        explicit_mode=execution_mode,
        execution_domain=execution_domain,
        merged_context=merged,
        trade_mode=trade_mode,
        offline_requested=offline_requested,
        gateway_url=gateway_url,
    )

    merged["execution_mode"] = mode
    merged["execution_domain"] = mode

    normalize_clock_value(merged, clock=clock, mode=mode)

    force_offline = apply_temporal_requirements(
        merged,
        mode=mode,
        as_of=as_of,
        dataset_fingerprint=dataset_fingerprint,
        gateway_url=gateway_url,
        offline_requested=offline_requested,
    )

    return ExecutionContextResolution(context=merged, force_offline=force_offline)


__all__ = [
    "ExecutionContextResolution",
    "merge_context",
    "normalize_default_context",
    "resolve_execution_context",
]
