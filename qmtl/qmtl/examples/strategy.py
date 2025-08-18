"""Strategy execution entry point."""

from qmtl.examples.dags.example_strategy import ExampleStrategy


def main() -> None:
    """Run the example strategy DAG and print the result."""
    result = ExampleStrategy().run()
    print(result)


if __name__ == "__main__":
    main()
