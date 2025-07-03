import importlib

import pytest

MODULES = [
    "examples.mode_switch_example",
    "examples.backfill_history_example",
    "examples.metrics_recorder_example",
    "examples.recorder_strategy",
    "examples.parallel_strategies_example",
]

@pytest.mark.parametrize("mod", MODULES)
def test_example_import(mod):
    assert importlib.import_module(mod) is not None
