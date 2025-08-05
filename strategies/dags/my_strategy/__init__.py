try:
    from nodes.generators import sample_generator
    from nodes.indicators import sample_indicator
    from nodes.transforms import sample_transform
except ModuleNotFoundError:  # pragma: no cover
    from strategies.nodes.generators import sample_generator
    from strategies.nodes.indicators import sample_indicator
    from strategies.nodes.transforms import sample_transform


class MyStrategy:
    """Custom strategy example for documentation purposes."""

    def __init__(self, config=None):
        self.config = config or {}

    def run(self):
        """Run the strategy logic."""
        data = sample_generator()
        metric = sample_indicator(data)
        print(sample_transform(metric))
