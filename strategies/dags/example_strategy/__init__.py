try:
    from nodes.generators import sample_generator
    from nodes.indicators import sample_indicator
    from nodes.transforms import sample_transform
except ModuleNotFoundError:  # pragma: no cover
    from strategies.nodes.generators import sample_generator
    from strategies.nodes.indicators import sample_indicator
    from strategies.nodes.transforms import sample_transform


class ExampleStrategy:
    """Simple example strategy template using sample node processors."""

    def __init__(self, config=None):
        self.config = config or {}

    def run(self):
        """Execute the strategy logic."""
        data = sample_generator()
        metric = sample_indicator(data)
        return sample_transform(metric)
