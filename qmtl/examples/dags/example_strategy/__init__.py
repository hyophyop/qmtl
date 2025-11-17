# from qmtl.examples.dags.example_strategy import *  # noqa: F403,F401

import sys
from typing import TYPE_CHECKING

# Create qmtl.examples.dags.example_strategy module
sys.modules["qmtl.examples.dags.example_strategy"] = sys.modules[__name__]

if TYPE_CHECKING:
    from qmtl.dag_manager import DAGManager as _DagManager
else:  # pragma: no cover - import at runtime only
    try:
        from qmtl.dag_manager import DAGManager as _DagManager
    except ModuleNotFoundError:
        class _DagManager:  # simple fallback for local execution
            def __init__(self):
                self.nodes = []

            def add_node(self, name, func, inputs=None):
                self.nodes.append((name, func, inputs or {}))

            def execute(self):
                results = {}
                for name, func, inputs in self.nodes:
                    kwargs = {k: results[v] for k, v in inputs.items()}
                    results[name] = func(**kwargs)
                return results

from qmtl.examples.nodes.generators import sequence_generator_node
from qmtl.examples.nodes.indicators import average_indicator_node
from qmtl.runtime.transforms import scale_transform_node


def build_dag():
    """Construct the example strategy DAG."""
    dag: _DagManager = _DagManager()
    dag.add_node("sequence", sequence_generator_node)
    dag.add_node("average", average_indicator_node, inputs={"data": "sequence"})
    dag.add_node("scaled", scale_transform_node, inputs={"metric": "average"})
    return dag


class ExampleStrategy:
    """DAG-based example strategy using reusable nodes."""

    def __init__(self, config=None):
        self.config = config or {}

    def run(self):
        dag = build_dag()
        result = dag.execute()
        return result["scaled"]
