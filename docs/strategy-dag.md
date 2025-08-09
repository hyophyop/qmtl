# Example Strategy DAG

This example demonstrates how to compose a strategy from reusable node processors connected by a DAG.

## Running the Example

1. Sync the environment and subtree (once):
    ```bash
    git fetch qmtl-subtree main
    git subtree pull --prefix=qmtl qmtl-subtree main --squash
    uv venv
    uv pip install -e qmtl[dev]
    ```
2. Execute the strategy:
    ```bash
    python strategies/strategy.py
    ```

The script builds the DAG defined in `strategies/dags/example_strategy` and prints the transformed result.
