class Node:
    """Represents a processing node in a strategy DAG."""

    def __init__(self, input=None, compute_fn=None, name=None, interval=None, period=None, tags=None):
        self.input = input
        self.compute_fn = compute_fn
        self.name = name
        self.interval = interval
        self.period = period
        self.tags = tags or []

    def __repr__(self):
        return f"Node(name={self.name!r}, interval={self.interval}, period={self.period})"


class StreamInput(Node):
    """Represents an upstream data stream placeholder."""

    def __init__(self, tags=None, interval=None, period=None):
        super().__init__(input=None, compute_fn=None, name="stream_input", interval=interval, period=period, tags=tags or [])
