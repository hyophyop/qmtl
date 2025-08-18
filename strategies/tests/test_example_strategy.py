"""Tests for the example strategy bundled with qmtl."""

from pathlib import Path
import sys

# Ensure qmtl's example nodes are importable. The ExampleStrategy module
# uses absolute ``from nodes...`` imports, so we add ``qmtl/examples`` to
# ``sys.path``.
sys.path.append(str(Path(__file__).resolve().parents[2] / "qmtl" / "qmtl" / "examples"))

from qmtl.examples.dags.example_strategy import ExampleStrategy


def test_example_strategy_runs():
    """ExampleStrategy should return scaled value."""
    assert ExampleStrategy().run() == 4

