DEFAULT_STRATEGY_TEMPLATE = '''"""Example QMTL Strategy.

This is a minimal strategy template. Customize the setup() method
to define your strategy logic.
"""

from qmtl.runtime.sdk import Strategy, StreamInput, ProcessingNode, Runner


class MyStrategy(Strategy):
    """A simple example strategy."""
    
    def setup(self):
        # Define input stream
        price = StreamInput(interval="1m", period=30)
        
        # Define processing logic
        def compute(view):
            # Your strategy logic here
            return view
        
        signal = ProcessingNode(
            input=price,
            compute_fn=compute,
            name="signal",
        )
        
        self.add_nodes([price, signal])


if __name__ == "__main__":
    # Submit strategy for evaluation
    result = Runner.submit(MyStrategy)
    print(f"Status: {result.status}")
'''

DEFAULT_ENV_EXAMPLE = '''# QMTL Configuration
# Uncomment and set these values for your environment

# Gateway URL (default: http://localhost:8000)
# QMTL_GATEWAY_URL=http://localhost:8000

# Default world (default: __default__)
# QMTL_DEFAULT_WORLD=__default__
'''
