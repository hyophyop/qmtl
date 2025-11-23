"""Smoke tests for public SDK shim modules."""

import importlib


def test_sdk_package_reexports_core_symbols():
    import qmtl.sdk as sdk
    import qmtl.runtime.sdk as runtime_sdk

    assert sdk.Node is runtime_sdk.Node
    assert sdk.CacheView is runtime_sdk.CacheView
    assert sdk.Runner is runtime_sdk.Runner


def test_sdk_submodules_passthrough_runtime_symbols():
    cases = [
        ("node", "Node"),
        ("cache_view", "CacheView"),
        ("runner", "Runner"),
    ]

    for module_name, symbol in cases:
        module = importlib.import_module(f"qmtl.sdk.{module_name}")
        runtime_module = importlib.import_module(f"qmtl.runtime.sdk.{module_name}")

        assert getattr(module, symbol) is getattr(runtime_module, symbol)
