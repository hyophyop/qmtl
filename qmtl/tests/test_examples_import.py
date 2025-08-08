import importlib

import pytest

MODULES = [
    "qmtl.examples.mode_switch_example",
    "qmtl.examples.backfill_history_example",
    "qmtl.examples.metrics_recorder_example",
    "qmtl.examples.recorder_strategy",
    "qmtl.examples.parallel_strategies_example",
    "qmtl.examples.multi_asset_lag_strategy",
    "qmtl.examples.templates.single_indicator",
    "qmtl.examples.templates.multi_indicator",
    "qmtl.examples.templates.branching",
    "qmtl.examples.templates.state_machine",
]

@pytest.mark.parametrize("mod", MODULES)
def test_example_import(mod):
    assert importlib.import_module(mod) is not None


def test_notebook_loads():
    import json
    from pathlib import Path

    nb = Path("notebooks/strategy_analysis_example.ipynb")
    data = json.loads(nb.read_text())
    assert "cells" in data
