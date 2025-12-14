"""Smoke tests for public SDK shim modules."""

import importlib


def test_sdk_package_reexports_core_symbols():
    """Test that qmtl.sdk exports v2 core API symbols."""
    import qmtl.sdk as sdk
    import qmtl.runtime.sdk as runtime_sdk

    # v2 core API
    assert sdk.Runner is runtime_sdk.Runner
    assert sdk.Strategy is runtime_sdk.Strategy
    assert sdk.SubmitResult is runtime_sdk.SubmitResult
    assert sdk.StrategyMetrics is runtime_sdk.StrategyMetrics


def test_sdk_submodules_passthrough_runtime_symbols():
    """Test that extended APIs are available via submodules."""
    # v2: Node, CacheView are in qmtl.runtime.sdk.node submodule
    from qmtl.runtime.sdk.node import Node
    assert Node is not None
