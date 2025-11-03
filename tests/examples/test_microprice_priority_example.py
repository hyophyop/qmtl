"""Smoke tests for the microprice/priority example pipeline."""

from __future__ import annotations

from examples.microprice_priority_strategy import (
    build_pipeline,
    simulate_single_snapshot,
)


def test_build_pipeline_returns_nodes() -> None:
    artifacts = build_pipeline()

    assert artifacts.entry_gate.inputs == [artifacts.microprice_metrics, artifacts.priority]


def test_simulate_single_snapshot_emits_gate_signal() -> None:
    snapshot = simulate_single_snapshot()

    assert snapshot["allow_entry"] in (True, False)
    assert snapshot["microprice"] is not None
    assert snapshot["imbalance"] is not None
