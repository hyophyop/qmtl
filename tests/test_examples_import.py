import importlib

import pytest

MODULES = [
    "qmtl.examples.mode_switch_example",
    "qmtl.examples.backfill_history_example",
    "qmtl.examples.metrics_recorder_example",
    "qmtl.examples.parallel_strategies_example",
    "qmtl.examples.multi_asset_lag_strategy",
]

@pytest.mark.parametrize("mod", MODULES)
def test_example_import(mod):
    assert importlib.import_module(mod) is not None
