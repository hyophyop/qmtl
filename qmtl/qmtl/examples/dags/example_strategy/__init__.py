try:
    from qmtl.dag_manager import DAGManager  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    class DAGManager:  # simple fallback for local execution
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

from nodes.generators.sequence import sequence_generator_node
from nodes.indicators.average import average_indicator_node
from qmtl.transforms import scale_transform_node


def build_dag():
    """Construct the example strategy DAG."""
    dag = DAGManager()
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
