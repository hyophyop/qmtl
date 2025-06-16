class Strategy:
    """Base class for strategies."""

    def __init__(self):
        self.nodes = []

    def add_nodes(self, nodes):
        self.nodes.extend(nodes)

    def setup(self):
        raise NotImplementedError

    # DAG serialization ---------------------------------------------------
    def serialize(self) -> dict:
        """Serialize strategy DAG using node IDs."""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
        }
