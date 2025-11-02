from __future__ import annotations

import itertools

import pytest

from qmtl.foundation.common.compute_context import ComputeContext
from qmtl.foundation.common.compute_key import compute_compute_key


@pytest.fixture
def base_context() -> ComputeContext:
    return ComputeContext(
        world_id="world-alpha",
        execution_domain="backtest",
        as_of="2024-01-01T00:00:00Z",
        partition="tenant-a",
    )


def test_compute_key_changes_when_any_component_differs(base_context: ComputeContext) -> None:
    node_hash = "node-123"
    original = compute_compute_key(node_hash, base_context)

    variants = [
        base_context.with_world("world-beta"),
        base_context.with_overrides(execution_domain="live"),
        base_context.with_overrides(as_of="2024-01-02T00:00:00Z"),
        base_context.with_overrides(partition="tenant-b"),
    ]

    for ctx in variants:
        assert compute_compute_key(node_hash, ctx) != original


@pytest.mark.parametrize(
    "domain",
    ["backtest", "dryrun", "live", "shadow"],
)
def test_compute_key_is_unique_per_execution_domain(domain: str, base_context: ComputeContext) -> None:
    node_hash = "node-xyz"
    context = base_context.with_overrides(execution_domain=domain)
    key = compute_compute_key(node_hash, context)
    assert key.startswith("blake3:")

    for other_domain in {"backtest", "dryrun", "live", "shadow"} - {domain}:
        other_ctx = base_context.with_overrides(execution_domain=other_domain)
        other_key = compute_compute_key(node_hash, other_ctx)
        assert other_key != key


def test_compute_key_stable_for_identical_context(base_context: ComputeContext) -> None:
    node_hash = "node-abc"
    key1 = compute_compute_key(node_hash, base_context)
    key2 = compute_compute_key(node_hash, base_context.with_overrides())
    assert key1 == key2

    clone = ComputeContext(
        world_id=base_context.world_id,
        execution_domain=base_context.execution_domain,
        as_of=base_context.as_of,
        partition=base_context.partition,
    )
    assert compute_compute_key(node_hash, clone) == key1


@pytest.mark.parametrize(
    "world,domain,as_of,partition",
    itertools.product(
        ["world-alpha", "world-beta"],
        ["backtest", "dryrun", "live", "shadow"],
        [None, "2024-01-01"],
        [None, "p0"],
    ),
)
def test_compute_key_hash_components_cover_domain_isolation(
    world: str,
    domain: str,
    as_of: str | None,
    partition: str | None,
) -> None:
    context = ComputeContext(
        world_id=world,
        execution_domain=domain,
        as_of=as_of,
        partition=partition,
    )
    node_hash = "node-hash"
    key = compute_compute_key(node_hash, context)

    mutated = context.with_world(f"{world}-alt") if as_of is not None else context
    if as_of is None:
        mutated = mutated.with_overrides(as_of="2025")
    else:
        mutated = mutated.with_overrides(as_of=None)
    assert compute_compute_key(node_hash, mutated) != key
