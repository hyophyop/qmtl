class Strategy:
    """Base class for strategies."""

    def __init__(self):
        self.nodes = []
        self.target = None

    def add_nodes(self, nodes):
        self.nodes.extend(nodes)

    def set_target(self, node_name):
        self.target = node_name

    def setup(self):
        raise NotImplementedError

    def define_execution(self):
        """Select the execution target if not already set."""
        if self.target is None and self.nodes:
            last = self.nodes[-1]
            self.target = last.name or last.node_id

    # DAG serialization ---------------------------------------------------
    def serialize(self) -> dict:
        """Serialize strategy DAG using node IDs."""
        if self.target is None:
            self.define_execution()
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "target": self.target,
        }
