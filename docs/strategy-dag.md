# Example Strategy DAG

This example demonstrates how to compose a strategy from reusable node processors connected by a DAG.

## Running the Example

1. Initialize the environment (once):
    ```bash
    git submodule update --init --recursive
    uv venv
    uv pip install -e qmtl[dev]
    ```
2. Execute the strategy:
    ```bash
    python strategies/strategy.py
    ```

The script builds the DAG defined in `strategies/dags/example_strategy` and prints the transformed result.
