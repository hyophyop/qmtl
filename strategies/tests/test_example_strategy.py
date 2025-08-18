from qmtl.examples.dags.example_strategy import ExampleStrategy


def test_example_strategy_runs():
    """ExampleStrategy should return scaled value."""
    assert ExampleStrategy().run() == 4

