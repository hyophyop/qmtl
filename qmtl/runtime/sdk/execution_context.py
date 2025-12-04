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
from qmtl.foundation.common.compute_context import evaluate_safe_mode


def normalize_default_context(
    context: Mapping[str, str | None] | None,
) -> dict[str, str] | None:
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


def merge_context(
    base: MutableMapping[str, str], source: Mapping[str, str | None] | None
) -> None:
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
    default_context: Mapping[str, str | None] | None,
    *,
    context: Mapping[str, str | None] | None,
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

    # Legacy execution_domain hints are ignored to enforce WS-first rules.
    merged.pop("execution_domain", None)

    mode = determine_execution_mode(
        explicit_mode=execution_mode,
        execution_domain=None,
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

    final_domain, downgraded, reason, safe_mode = evaluate_safe_mode(
        merged.get("execution_domain"), merged.get("as_of")
    )
    merged["execution_domain"] = final_domain or merged.get("execution_domain") or ""
    if downgraded:
        merged["downgraded"] = "true"
    if reason is not None:
        merged["downgrade_reason"] = getattr(reason, "value", str(reason))
    if safe_mode:
        merged["safe_mode"] = "true"

    return ExecutionContextResolution(
        context=merged,
        force_offline=force_offline,
        downgraded=downgraded,
        downgrade_reason=getattr(reason, "value", None) if reason is not None else None,
        safe_mode=safe_mode,
    )


__all__ = [
    "ExecutionContextResolution",
    "merge_context",
    "normalize_default_context",
    "resolve_execution_context",
]
