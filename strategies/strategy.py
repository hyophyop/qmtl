"""Strategy execution entry point.

Refer to docs/alphadocs/Kyle-Obizhaeva_non-linear_variation.md for market impact background.
"""

from strategies.dags.example_strategy import ExampleStrategy


def main():
    """Run the example DAG strategy.

    The same nodes (e.g., ``average_indicator_node``) can be reused in other DAGs
    to build new strategies without modifying the node implementations.
    """
    result = ExampleStrategy().run()
    print(result)


if __name__ == "__main__":
    main()
