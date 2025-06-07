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
        raise NotImplementedError
