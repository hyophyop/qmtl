"""Top-level pytest configuration.

Expose optional fixture plugins globally to satisfy pytest's requirement that
``pytest_plugins`` be declared in a top-level conftest when it should affect
the entire suite.
"""

pytest_plugins = (
    "tests.e2e.world_smoke.fixtures_inprocess",
    "tests.e2e.world_smoke.fixtures_docker",
)

